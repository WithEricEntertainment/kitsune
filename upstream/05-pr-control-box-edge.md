**Title:** Act on a control box press once, not on every loop pass (3 of 5 in the host-protocol series)

A small preparation for the USB link PR that follows; it is the only change to the main loop.

The main loop calls `engine.reset()` whenever the board is locked and the control box button reads high. Today `reset()` unlocks the board, so the loop stops calling it and nothing repeats. Once a host can be connected (next PR), a reset leaves the board locked and closed, so a held button would re-run `reset()` on every pass of the loop. I saw this on a real board: about 110 identical `STATE` lines a second pushed to the host for as long as the button was held.

This reacts to the rising edge instead, with a 50 ms bounce guard. 10 lines added, 4 removed, all in `Firmware/main.py`.

**Standalone behaviour:** unchanged for normal use. One edge case differs: a control button that is already held down when a round is won no longer resets the board until it is pressed again. Pressing and releasing it, as normal, works as before. I re-checked the standalone flow on a Kitsune++ v1.1.0 after this change.

Stacked on the engine PR, whose commits appear in the diff until it merges.
