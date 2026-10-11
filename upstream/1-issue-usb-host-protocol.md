**Title:** USB serial control protocol (arm/close/reset from a host, first-press events back)

Hi, and thanks for Kitsune. I bought a Kitsune++ v1.1.0 to run quiz nights from a computer. The README's TODO ("implement USB device identity, to work with buzzin.live etc") is close to what I ended up needing, so I built a small host-control layer and tested it on the real board. I'm opening this to ask whether you'd want it upstream, with no obligation either way.

**What it does**

A line-based text protocol over the Pico's USB serial port. The host sends `HELLO 1`, `ARM <n> <ports>`, `CLOSE`, `RESET`, `STATUS`, `BYE`. The board replies with `OK`/`ERR`/`STATE` lines and sends `BUZZ <n> <port>` when a player wins. The board still decides the winner itself, so the host never sits in the decision path. With no host connected the board behaves exactly as it does today (the control box still works).

Full spec: `PROTOCOL.md` in my fork. Code: `protocol.py` (parser and state, no hardware imports, unit-testable on a normal computer), `hostlink.py` (serial I/O), and small changes to `engine.py` and `main.py`. 69 unit tests run under plain pytest.

**Tested on a real v1.1.0 board (MicroPython 1.27)**

Every command and error reply; a real press producing `BUZZ` then the locked state; reconnect (state survives a dropped connection; unplug and replug reboots to standalone); 20 near-simultaneous presses between two boxes giving exactly one winner each time; no delay when nothing is reading the port; one-cable power (27V buzzer) with no resets. It now also runs a real quiz night's console (a browser using Web Serial) end to end.

**Things I found on the way**

- Two real bugs in my own first version, only visible on the board: raising an exception class that called `Exception.__init__` crashed MicroPython, and holding the control box button re-ran reset on every loop pass, flooding the host with state lines. Both are fixed in the fork (reset now acts once per press).
- Reading both inputs at microsecond resolution showed my own hands differed by about 8 ms, far more than any board effect. `Tools/edge_timing.py` and `BENCH_FAIRNESS_2026-10-10.md` in the fork have the script and results.
- Linux ModemManager probes a newly attached serial device, and the stray bytes can make the next command fail once. The board now drops control characters from its input, and the protocol notes say hosts should send a blank line first.
- My board shipped with the v1.1.0 pin map selected (default volume 7) while `main` selects the v1.0 map (volume 30). The pins are identical, so I assume this is the designer's per-board volume setting.

**An optional extra: roll-call**

A `CHECK` command puts every port live so each first press lights its LED and keeps it lit, with no lockout and no sound, so a host can see which buzzers are in the room before a game. It is small (about 40 lines plus tests) and entirely separable; I'm happy to leave it out of any PR.

**Questions**

1. Is this something you'd want, as a PR or just as a reference?
2. If a PR, would you prefer it split (parser, engine changes, USB link) or as one? I have it as three branches already.
3. Any concerns about the Ctrl-C handling while a host is connected (the protocol turns it off between `HELLO` and `BYE`, with `BYE` restoring it)?

Fork: github.com/WithEricEntertainment/kitsune (branches `feature/host-command-parser`, `feature/engine-state-machine`, `feature/usb-serial-protocol`; everything together on `beventra-integration`).
