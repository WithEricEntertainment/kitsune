**Title:** Optional: add a CHECK roll-call command (4 of 4)

An optional extra on top of the USB link PR, easy to leave out.

`CHECK` puts every port live so each port's first press lights its LED and keeps it lit, with no lockout and no sound. A host can use it to see which buzzers are in the room before a game. The board has no timer: the host ends it with `RESET`, `CLOSE`, `ARM` or `BYE` (or the control box does), which also puts the LEDs out. The board pushes `STATE <arm> CHECK <ids>` as the set grows. An older firmware answers `CHECK` with `ERR UNKNOWN`, so a host can tell whether it is supported.

**Changes:** `Firmware/protocol.py` (a `CHECK` mode and the set of pressed ports), `Firmware/engine.py` (light the LED on a first press, no buzz), `PROTOCOL.md`, and 17 tests (86 total).

**Tested on a Kitsune++ v1.1.0:** two boxes pressed together each pushed one `STATE ... CHECK` line, the set grew in order, the LEDs stayed lit until `RESET`, then went out. Silent.
