**Title:** Set `player_box.led` to `None` when no LED is passed

`player_box.update_led()` reads `self.led`, but `__init__` only assigned it when an LED object was passed in. A box built without one raised `AttributeError` on the first `update_led()` call.

This assigns `self.led = led_obj` unconditionally (`None` when absent). No change for boxes that have an LED. Checked on CPython with stubbed `machine`: before, `AttributeError: 'player_box' object has no attribute 'led'`; after, `update_led(True)` is a no-op.

Branch: `fix/player-box-led-attribute` (one commit off `main`).
