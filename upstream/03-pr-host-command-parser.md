**Title:** Add a hardware-free host command parser and arbiter (1 of 4)

First of four small PRs that add an optional USB serial control protocol, so a computer can arm, close and reset the buzzers and be told who buzzed first. The board still decides the winner, and with no computer connected it behaves exactly as it does today. Later PRs wire this into the engine and the USB link; this one only adds files, so nothing about the board's behaviour changes.

**Adds**
- `Firmware/protocol.py`: parses command lines (`HELLO`, `ARM`, `CLOSE`, `RESET`, `STATUS`, `BYE`) and holds the arbitration state (`STANDALONE`, `CLOSED`, `ARMED`, `LOCKED`). It has no hardware imports, so the same file runs under normal Python and on the board.
- `Tests/test_protocol.py`: 45 tests that run on a computer with plain `pytest`.
- `requirements-dev.txt`: the host-side tools (`pytest`, `mpremote`) and how to use them.

**Notes for review**
- A standalone board starts locked until the control box opens it, as it does today (`self.locked = True` at startup).
- `ProtocolError` stores its code without calling `Exception.__init__`: that call crashed MicroPython on the board (a CPython-only test can't catch it).

Tested with `pytest Tests` (45 passed). Part of the series: parser (this), engine, USB link, optional roll-call.
