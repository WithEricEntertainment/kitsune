Subject: Kitsune++ arrived and works, and some small PRs if you'd like them

Hi Aisling,

The set arrived and it's great. I've been running it from a computer over the middle USB-C port, and it has been solid: one cable powers it with the 27V buzzer, with no resets, and the buttons, LEDs and control box all behave as they should.

As I mentioned, I wrote a small serial command protocol so software can arm, close and reset the buzzers and be told who buzzed first, and I've now tested it on the real board. I'd like to offer it back, plus two small fixes I found on the way. They're all on my fork (github.com/WithEricEntertainment/kitsune), and I'd open them as pull requests (the first two are independent fixes, the rest is the protocol series) if you're happy for me to:

1. `player_box.led` is never set when no LED is passed, so `update_led()` would raise. One-line fix.
2. In `shims.py`, `type(pin_obj) == "VirtualPin"` compares a class to a string, so it is always false and the MCP branches never run. I removed the dead branches rather than switching them on, because the read branch calls `VirtualPin.input()`, which returns nothing and would make the four DIP switches read `None`. I checked on the board that the DIP switch reads and all ten LED writes are identical before and after.
3. to 7. The host protocol, as five small stacked PRs so each is easy to review: the parser and state machine (no hardware code, with tests that run on a normal computer), the engine changes, a small main-loop change so the control box acts once per press, the USB serial link (with a protocol document), and an optional "roll-call" command that lights each port's LED on its first press so you can see which buzzers are in the room.

Nothing changes for anyone who doesn't connect a computer: with no host the board behaves exactly as it does today, including the control box. If you'd rather I split these differently, or leave some out, just say.

Two questions while I have you:
- The board I received had the v1.1.0 pin map selected in its own `pinouts.py` (default volume 7), while `main` selects the v1.0 map (volume 30). The pins are identical, so I assumed that's your per-board volume setting. Should `main` select the map per board, or is the repo copy meant as a general default?
- While a computer is connected, the protocol turns off Ctrl-C between `HELLO` and `BYE`, so a running script can't be interrupted over serial (`BYE` gives it back). Any concerns with that?

Thanks again for making these and sharing the design.

Eric
