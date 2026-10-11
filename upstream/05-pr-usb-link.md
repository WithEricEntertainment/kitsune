**Title:** Add the USB serial host link and PROTOCOL.md (3 of 4)

Builds on the engine PR. Adds the serial side and a document describing the protocol.

**Adds**
- `Firmware/hostlink.py`: reads commands from `stdin` without blocking, hands them to the engine, and sends replies as lines starting with `KIT ` (so hosts can ignore the firmware's ordinary `print()` output). `HELLO` starts a session and `BYE` ends it; Ctrl-C is switched off only between the two, so a runaway script can still be interrupted in standalone mode. Control characters in the input are dropped, so line noise or a modem probe cannot corrupt a command.
- `Firmware/main.py`: starts the link, polls it in the main loop, and restores Ctrl-C in a `finally` if the script exits.
- `PROTOCOL.md`: the wire format, modes, replies and errors, reconnection behaviour, and what was verified on a real board.
- `Tests/test_hostlink.py`.

**A bug this fixes in the main loop.** The control box handler ran `reset()` on every pass of the loop while the button was held. Standalone that is harmless, but on a hosted link it floods the host with about 110 identical `STATE` lines a second. It now acts once per press (rising edge, 50 ms bounce guard).

**Tested on a Kitsune++ v1.1.0 (MicroPython 1.27):** every command and error reply; a real press giving `BUZZ` then `LOCKED`; reconnect (state survives a dropped connection, and an unplug reboots to standalone); 20 near-simultaneous presses across two boxes giving exactly one winner each time; no delay with nothing reading the port; one-cable power with the 27V buzzer. Standalone flow with the control box re-checked after the loop change. 69 unit tests pass with `pytest Tests`.

**Question:** the protocol turns Ctrl-C off while a host is connected and gives it back on `BYE`. Any concern with that?

Stacked on the engine and parser PRs, so the diff includes their commits until those are merged.
