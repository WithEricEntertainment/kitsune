**Title:** `UnifiedPin` never takes its MCP23017 path (`type(pin_obj) == "VirtualPin"` is always False)

In `Firmware/lib/shims.py`:

```python
self.is_virtual = (True if type(pin_obj) == "VirtualPin" else False)
```

`type(pin_obj)` is a class and `"VirtualPin"` is a string, so this is always `False`. Every `UnifiedPin` therefore takes the native-`Pin` branch, including the ones wrapping MCP23017 pins (LEDs and DIP switches on the ++ boards). It works today only because the native branch happens to do the right thing for `VirtualPin`: writes go through `VirtualPin.value(val)`, and reads go through `not VirtualPin.value()`.

**Why I'm not sending a one-line fix**

The obvious fix (`type(pin_obj).__name__ == "VirtualPin"`) would switch DIP-switch reads to the virtual branch, which calls `self.obj.input()`. In `mcp23017.py`, `VirtualPin.input()` sets the pin to input mode and returns nothing. I checked this on a v1.1.0 board:

```
is_virtual flags: [False, False, False, False]
type name: VirtualPin | type == 'VirtualPin': False
current path  switch.value(pullup=True): [False, False, False, False]
raw VirtualPin.value(): [1, 1, 1, 1]
raw VirtualPin.input() (what the fixed branch would call): [None, None, None, None]
```

So with the check "fixed", the four DIP switches would all read `None`, and the debug / mute / test-speaker / autoreset settings would silently stop working.

A correct change needs the virtual branch to read `VirtualPin.value()` and keep the inversion for pull-ups, or the dead branch should simply be removed. That is your call, since it touches how the switches are read. Happy to send a PR for whichever you prefer, tested on the board.
