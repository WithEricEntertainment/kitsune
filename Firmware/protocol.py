# Host-control protocol: command parsing and first-press arbitration.
#
# No hardware imports on purpose, so this runs unmodified under plain
# CPython (Tests/test_protocol.py) and on the device. Nothing here prints or
# reads stdin; callers feed it lines and send back whatever lines it returns.
#
# Wire format is one space-delimited line per message.
#   host -> device:  HELLO 1 | ARM <arm> <ids> | CLOSE [<arm>] | RESET [<arm>] | STATUS | BYE
#   device -> host:  OK <cmd> [...] | ERR <code> | STATE <arm> <state> [...] | BUZZ <arm> <id>

PROTO_VERSION = 1

STANDALONE = "STANDALONE"  # no host: physical control box in charge
CLOSED = "CLOSED"  # host connected, nobody may win
ARMED = "ARMED"  # host connected, listed players may win
LOCKED = "LOCKED"  # host connected, a winner is held until RESET/ARM


class ProtocolError(Exception):
    def __init__(self, code):
        Exception.__init__(self, code)
        self.code = code


def parse_command(line):
    """Turn one input line into (name, args). Raises ProtocolError.

    Only the shape is checked here (argument count, integers); whether a
    player ID exists or the command is legal right now is up to Arbiter.
    """
    parts = line.split()
    if not parts:
        raise ProtocolError("EMPTY")
    name = parts[0].upper()
    args = parts[1:]

    if name == "HELLO":
        if len(args) != 1:
            raise ProtocolError("SYNTAX")
        return name, [_int(args[0])]
    if name == "ARM":
        if len(args) != 2:
            raise ProtocolError("SYNTAX")
        ids = [p.upper() for p in args[1].split(",")]
        if "" in ids:
            raise ProtocolError("SYNTAX")
        return name, [_int(args[0]), ids]
    if name == "CLOSE" or name == "RESET":
        if len(args) > 1:
            raise ProtocolError("SYNTAX")
        return name, [_int(args[0])] if args else []
    if name == "STATUS" or name == "BYE":
        if args:
            raise ProtocolError("SYNTAX")
        return name, []
    raise ProtocolError("UNKNOWN")


def _int(text):
    try:
        value = int(text)
    except ValueError:
        raise ProtocolError("SYNTAX")
    if value < 1:
        raise ProtocolError("SYNTAX")
    return value


class Arbiter:
    """Authoritative game state. The engine calls press()/control_press();
    the serial loop calls handle_line(). Both return protocol lines to send.

    In STANDALONE the first press wins and the control button clears it,
    matching the pre-protocol behaviour. Arm numbers are chosen by the host
    and must strictly increase, so a repeated or late ARM is rejected.
    """

    def __init__(self, player_ids):
        self.player_ids = list(player_ids)  # every port, in report order
        self.mode = STANDALONE
        self.arm = 0
        self.mask = []
        self.winner = None

    def state_line(self):
        if self.mode == ARMED:
            return "STATE %d ARMED %s" % (self.arm, ",".join(self.mask))
        if self.mode == LOCKED:
            return "STATE %d LOCKED %s" % (self.arm, self.winner)
        return "STATE %d %s" % (self.arm, self.mode)

    def press(self, player_id):
        """A button was pressed. Returns (won, lines); lock happens first."""
        if self.mode == STANDALONE:
            if self.winner is not None or player_id not in self.player_ids:
                return False, []
            self.winner = player_id
            return True, []
        if self.mode != ARMED or player_id not in self.mask:
            return False, []
        self.mode = LOCKED
        self.winner = player_id
        self.mask = []
        return True, ["BUZZ %d %s" % (self.arm, player_id), self.state_line()]

    def control_press(self):
        """Physical control box. Standalone: clear the winner. Hosted: same
        as RESET (clear and stay closed), pushed so the host is never stale."""
        if self.mode == STANDALONE:
            self.winner = None
            return []
        self._clear()
        return [self.state_line()]

    def handle_line(self, line):
        try:
            name, args = parse_command(line)
        except ProtocolError as e:
            if e.code == "EMPTY":
                return []
            return ["ERR " + e.code]
        try:
            return self._run(name, args)
        except ProtocolError as e:
            # Always follow an error with state so the host can reconcile.
            return ["ERR " + e.code, self.state_line()]

    def _run(self, name, args):
        if name == "HELLO":
            if args[0] != PROTO_VERSION:
                raise ProtocolError("VERSION")
            if self.mode == STANDALONE:
                self.mode = CLOSED
                self.winner = None
            # Already hosted: a reconnect. Keep state, just report it.
            return ["OK HELLO %d" % PROTO_VERSION, self.state_line()]

        if name == "BYE":
            self.mode = STANDALONE
            self.mask = []
            self.winner = None
            return ["OK BYE", self.state_line()]

        if self.mode == STANDALONE:
            raise ProtocolError("NOHOST")

        if name == "STATUS":
            return ["OK STATUS", self.state_line()]

        if name == "ARM":
            arm, ids = args
            if arm <= self.arm:
                raise ProtocolError("STALE")
            for pid in ids:
                if pid not in self.player_ids:
                    raise ProtocolError("BADID")
            self.arm = arm
            self.winner = None
            self.mask = [p for p in self.player_ids if p in ids]
            self.mode = ARMED
            return ["OK ARM %d" % arm, self.state_line()]

        # CLOSE / RESET: an arm number, if given, must be the current one.
        if args and args[0] != self.arm:
            raise ProtocolError("STALE")
        if name == "CLOSE":
            if self.mode == ARMED:
                self.mode = CLOSED
                self.mask = []
            # LOCKED keeps its winner; CLOSED is already closed.
        else:
            self._clear()
        return ["OK " + name, self.state_line()]

    def _clear(self):
        self.mode = CLOSED
        self.mask = []
        self.winner = None
