**Title:** Drive the engine's locked/winner state from the arbiter (2 of 5)

Builds on the parser PR. Adds the engine hooks the host protocol needs, with standalone behaviour unchanged.

**Changes (`Firmware/engine.py`)**
- `locked` becomes a property derived from the arbiter, so one state machine decides whether a press can win, in standalone and hosted modes alike.
- `handle_buzz` asks the arbiter first and returns early if the press did not win. The lock happens before anything slow (LED, pixel, the ~625 ms buzz), and a `BUZZ` line is emitted to the host before the sound starts.
- New `handle_command(line)` for host lines, and an optional `emit` callback that sends protocol lines out (a no-op when nothing is connected).
- Autoreset is ignored while a host is connected, so a host never sees the board reopen on its own timer.
- `reset()` is the control box: standalone reopens as before; hosted, it clears the winner and stays closed.
- The 20 ms debounce after a reset is only applied when the board reopens in standalone, as the old code did.

**Tests:** `Tests/test_engine.py` (13 new, 58 total) drives the engine with fake `machine` modules, covering press, lock, reset and autoreset in both modes.

Because this PR is stacked on the parser PR its diff includes those commits until the parser PR is merged.
