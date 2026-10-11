"""HostLink tests on a laptop, using the fake engine hardware from test_engine."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Firmware"))

from test_engine import make  # noqa: E402  (also installs the MicroPython fakes)
from hostlink import HostLink, MAX_LINE  # noqa: E402


class Wire:
    """Fake serial port: feed() puts input on the wire, out collects output."""

    def __init__(self):
        self.incoming = []
        self.out = ""
        self.intr = []

    def feed(self, text):
        self.incoming.extend(text)

    def read_char(self):
        return self.incoming.pop(0) if self.incoming else ""

    def lines(self):
        return [l for l in self.out.split("\n") if l]


def link():
    e, players, led, events, sent, cfg = make()
    w = Wire()
    hl = HostLink(e, w.read_char, lambda s: setattr(w, "out", w.out + s), w.intr.append)
    return hl, e, players, w


def test_replies_are_prefixed():
    hl, e, p, w = link()
    w.feed("HELLO 1\n")
    hl.poll()
    assert w.lines() == ["KIT OK HELLO 1", "KIT STATE 0 CLOSED"]


def test_line_split_across_polls_and_crlf():
    hl, e, p, w = link()
    w.feed("HEL")
    hl.poll()
    assert w.out == ""
    w.feed("LO 1\r\n")
    hl.poll()
    assert w.lines()[0] == "KIT OK HELLO 1"


def test_control_characters_inside_a_line_are_dropped():
    hl, e, p, w = link()
    w.feed("\x00\x1b\x03HEL\x7fLO\x01 1\n")
    hl.poll()
    assert w.lines()[0] == "KIT OK HELLO 1"


def test_control_characters_alone_do_not_make_an_error():
    hl, e, p, w = link()
    w.feed("\x00\x01\x02\n")
    hl.poll()
    # An empty line is what a blank line already is: no reply and no error
    assert "ERR" not in w.out


def test_ctrl_c_disabled_only_while_hosted():
    hl, e, p, w = link()
    w.feed("STATUS\n")
    hl.poll()
    assert w.intr == []  # standalone: untouched
    w.feed("HELLO 1\n")
    hl.poll()
    assert w.intr == [-1]
    w.feed("STATUS\nSTATUS\n")
    hl.poll()
    assert w.intr == [-1]  # not re-sent
    w.feed("BYE\n")
    hl.poll()
    assert w.intr == [-1, 3]


def test_close_restores_ctrl_c():
    hl, e, p, w = link()
    w.feed("HELLO 1\n")
    hl.poll()
    hl.close()
    assert w.intr == [-1, 3]
    hl.close()  # harmless twice
    assert w.intr == [-1, 3]


def test_commands_before_hello_rejected():
    hl, e, p, w = link()
    w.feed("ARM 1 A1\n")
    hl.poll()
    assert w.lines()[0] == "KIT ERR NOHOST"


def test_buzz_is_sent_prefixed_before_sound():
    hl, e, p, w = link()
    order = []
    e.buzz = lambda *a, **k: order.append(("buzz", w.out))
    w.feed("HELLO 1\nARM 5 A1,A2\n")
    hl.poll()
    e.handle_buzz(p["A2"])
    _, out_at_buzz = order[0]
    assert "KIT BUZZ 5 A2\n" in out_at_buzz  # already on the wire when the sound starts
    assert w.lines()[-2:] == ["KIT BUZZ 5 A2", "KIT STATE 5 LOCKED A2"]


def test_overlong_line_rejected_then_recovers():
    hl, e, p, w = link()
    w.feed("X" * (MAX_LINE + 50) + "\n")
    hl.poll()
    assert w.lines() == ["KIT ERR TOOLONG"]
    w.feed("HELLO 1\n")
    hl.poll()
    assert w.lines()[1] == "KIT OK HELLO 1"


def test_garbage_gets_error_not_crash():
    hl, e, p, w = link()
    w.feed("\x00\x01 ??\nHELLO 1\n")
    hl.poll()
    assert w.lines()[0].startswith("KIT ERR")
    assert "KIT OK HELLO 1" in w.lines()


def test_flood_does_not_stall_poll():
    hl, e, p, w = link()
    w.feed("HELLO 1\n" * 1000)
    hl.poll()  # bounded work per call
    assert len(w.incoming) > 0
