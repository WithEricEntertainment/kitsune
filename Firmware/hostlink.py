# Serial link between the host (over USB) and the engine.
#
# Reads command lines from stdin without blocking, hands them to the engine,
# and sends replies as lines starting with "KIT ". The prefix lets the host
# ignore the firmware's ordinary print() output on the same stream.
#
# Ctrl-C (0x03) is switched off only while a host is connected (after HELLO,
# until BYE), so a runaway script can still be interrupted in standalone mode.
# The I/O is passed in, so this can be tested on a laptop; usb_link() wires it
# to the real stdin/stdout on the board.

from protocol import STANDALONE

PREFIX = "KIT "
MAX_LINE = 96
MAX_CHARS_PER_POLL = 256  # keep the main loop responsive if the host floods us


class HostLink:
    def __init__(self, engine, read_char, write, set_intr):
        """read_char() -> one character, or "" if none waiting.
        write(text) sends text. set_intr(-1) disables Ctrl-C, set_intr(3) restores it."""
        self.engine = engine
        self.read_char = read_char
        self.write = write
        self.set_intr = set_intr
        self.buf = ""
        self.too_long = False
        self.hosted = False
        engine.emit = self.send

    def send(self, lines):
        for line in lines:
            self.write(PREFIX + line + "\n")

    def poll(self):
        """Process whatever input has arrived. Call from the main loop."""
        for _ in range(MAX_CHARS_PER_POLL):
            ch = self.read_char()
            if not ch:
                return
            if ch == "\n":
                self._finish_line()
            elif ch != "\r":
                if len(self.buf) < MAX_LINE:
                    self.buf += ch
                else:
                    self.too_long = True

    def close(self):
        """Give Ctrl-C back (call if the script is exiting)."""
        if self.hosted:
            self.hosted = False
            self.set_intr(3)

    def _finish_line(self):
        line, too_long = self.buf, self.too_long
        self.buf = ""
        self.too_long = False
        if too_long:
            self.send(["ERR TOOLONG"])
            return
        self.engine.handle_command(line)
        hosted = self.engine.arbiter.mode != STANDALONE
        if hosted != self.hosted:
            self.hosted = hosted
            self.set_intr(-1 if hosted else 3)


def usb_link(engine):
    """Build a HostLink on the board's USB serial (stdin/stdout)."""
    import sys
    import select
    import micropython

    poller = select.poll()
    poller.register(sys.stdin, select.POLLIN)

    def read_char():
        return sys.stdin.read(1) if poller.poll(0) else ""

    return HostLink(engine, read_char, sys.stdout.write, micropython.kbd_intr)
