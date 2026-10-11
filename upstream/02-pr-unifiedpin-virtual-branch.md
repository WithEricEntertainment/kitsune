**Title:** Remove the never-true VirtualPin branch from `UnifiedPin`

In `Firmware/lib/shims.py`, `self.is_virtual = (True if type(pin_obj) == "VirtualPin" else False)` compares a class with a string, so it is always `False`. Every `UnifiedPin`, including the ones wrapping MCP23017 pins (the LEDs and the DIP switches), already takes the native-`Pin` path, and that is the path that has been running all along.

The virtual branches were not just unused; switching them on would break things. The read branch calls `VirtualPin.input()`, which sets the pin to input mode and returns nothing. On a v1.1.0 board that gives `[None, None, None, None]` for the four DIP switches, so debug, mute, test-speaker and autoreset would silently stop working.

So this removes the dead branches and keeps the path that works. `VirtualPin` has the same `value()` interface as `Pin` (read with no argument, write with one), so one path serves both. No behaviour change, 8 lines added and 10 removed.

**Checked on a v1.1.0 board** by running the old and new `UnifiedPin` side by side on the same pins:
- DIP switches, with switches 1 and 3 on and 2 and 4 off, then again with all four off: config reads (`value(pullup=1)`), debug-loop reads (`value(pullup=True)`) and plain reads were identical, e.g. `[True, False, True, False]` both ways.
- LEDs: turning each of the ten LEDs on and off wrote identical values to the MCP23017 output registers.

If you did intend the virtual branch to be live, with the MCP doing the inversion (`polarity=1`), I'm happy to do that instead, but it changes how the switches are read, so I held off.

Branch: `fix/unifiedpin-dead-virtual-branch` (one commit off `main`; the file uses CRLF line endings, kept).
