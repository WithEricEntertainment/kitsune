# CLAUDE.md — Beventra integration fork

This is a fork of [Amekyras/kitsune](https://github.com/Amekyras/kitsune), a MicroPython-based
lockout buzzer system for quiz/trivia. This fork's purpose is narrow: add a USB serial control
protocol so an external app (Beventra, a separate Node/TypeScript trivia-hosting platform — not
in this repo) can drive the buzzer set instead of relying only on the physical control box.

**Status (2026-09-29): Kitsune is the confirmed hardware target**, not a tentative pick — decided
after a full bake-off against commercial USB-keypad systems, closed standalone systems, and DIY
open-source builds, none of which offer both real assembled hardware and a host-controllable
arm/close/reset loop. Full reasoning: Beventra repo's
`docs/product/decisions/DEC-010_BUZZER_HARDWARE_SELECTION.md`. The integration itself is tracked as
Beventra's `WI-1418`, currently blocked on that app's own playoff-UI work (`WI-1417`) landing first
— this firmware work is independently useful in the meantime and isn't gated on that.

**Also decided on the Beventra side (`DEC-011_BUZZ_INPUT_ABSTRACTION.md`)**: the feature is built
against a source-agnostic event contract — `{ slotId, timestamp, source }` — shared across three
input methods (Kitsune, a documented-but-not-scheduled phone path, and an unblocked
keyboard-simulated POC used to validate the design before real hardware is in the loop). **This
requires no protocol change here** — Kitsune's existing `BUZZ <arm#> <playerId>` design (below)
already produces exactly this shape; `playerId` *is* the slot identifier for this source. Worth
knowing this mapping exists so the wire protocol doesn't drift from what the Beventra side expects,
but nothing in "What to build" changes because of it.

**Do not treat this as a general refactor.** Scope every change to what's needed for the protocol
below. The existing owner (Aisling Skeet) maintains this project for their own community
(quizbowl societies); keep changes minimal, readable, and plausible as an eventual upstream PR —
see "Upstream" at the bottom.

**Before writing protocol code, read `BEVENTRA_INTEGRATION_PLAN.md`.** This file specifies *what*
the protocol must do; that one specifies *how* to build it in this codebase — the actual sequencing,
state-machine design, and open questions to resolve first.

## Hardware in hand

Purchased unit: **Kitsune++ v1.1.0**. In `Firmware/pinouts.py`, `board_pins` currently defaults to
`p10v1_pins` (the v1.0 pin map) — **this is wrong for this board and must be changed to
`p10v1p1_pins`** before anything else, and verified against the real hardware (buzz, LEDs, control
button) before touching protocol code.

USB-C is already present on the central control box and already exposes MicroPython's serial REPL
— no hardware/connector change is needed, only firmware changes to add a real command protocol on
top of (or instead of) the raw REPL.

## Current firmware architecture (as of the fork point)

- `Firmware/main.py` — boot, hardware init, a `debug` mode that polls buttons and prints state,
  then a tight main loop that only checks the physical control button for reset while
  `engine.locked`.
- `Firmware/engine.py` — `kitsune_engine` holds `locked` / `refractory` state and `active_player`.
  `handle_buzz()` is called (via `micropython.schedule`) on an IRQ-driven button press, locks
  immediately, sets a NeoPixel color by team (`"A" in player.id` / `"B" in player.id`), and then
  **calls `self.buzz()` synchronously** — a ~625ms sequence of blocking `utime.sleep_ms()` calls
  driving the PWM speaker. Only after that returns does it optionally schedule an auto-reset timer.
  This blocking call is exactly what the protocol work below needs to move out of the
  timing-critical decision path (per requirement 2).
- `Firmware/pinouts.py` — per-board pin maps (`p8_pins`, `p10_pins`, `p10v1_pins`,
  `p10v1p1_pins`), each with `ids` like `["A1".."A5", "B5".."B1"]`. Only two teams (`A`/`B`) exist
  at the firmware level today — that's fine, Beventra owns the actual team assignment
  (left/center/right, 2 players each) on the host side; firmware just needs to report which
  physical player ID/port buzzed.
- `Firmware/user_cfg.py` — end-user volume/color/frequency/autoreset config. `reset_duration`
  (autoreset) must end up disabled for Beventra-driven games per requirement 5.
- `Firmware/factory.py` / `Firmware/switchboard.py` — hardware init and runtime config assembly
  from DIP switches; not expected to need changes, but check before assuming.

## What to build: the serial protocol

Beventra's host console will open this device's USB serial port via the browser's Web Serial API
and drive it directly — the Kitsune side must do local first-press arbitration (never trust
message arrival order in the browser to determine a winner) and must remain authoritative about
game state.

Implement a small, versioned, line-delimited command/event protocol:

1. **Clean channel.** Diagnostics currently printed to the REPL (`print(...)` calls throughout
   `main.py`/`engine.py`) must be distinguishable from protocol lines, or removed from the
   production path. Don't assume raw `print()` is a two-way control interface — implement real
   command parsing on stdin without REPL prompts corrupting it.
   **Resolved:** the REPL doesn't compete with a running script for `sys.stdin` — `main.py` owns
   the stream while it runs. The one thing that does intercept bytes unconditionally is Ctrl-C
   (`0x03`); `micropython.kbd_intr(-1)` disables that capture, documented by MicroPython
   specifically "in case that stream is used for other purposes." See the plan doc for how this
   gets scoped (not left on from boot).
2. **Winner-lock-first, notify-after.** On an eligible button press: record and lock the winner
   *before* anything else, light that player's existing LED, then emit one `BUZZ` event carrying
   player ID and a monotonically increasing round/arm number. Move `engine.buzz()`'s blocking sound
   routine out of this critical path (e.g. queue it / run it after the lock+emit, or make it
   non-blocking). Local arbitration stays on-device; the network round-trip to Beventra must never
   be in the decision path.
3. **Commands:** `ARM <arm#> <eligible player IDs>`, `CLOSE`, `RESET`, `STATUS`.
   - `ARM` clears the previous winner's LED and enables only the listed players; all others'
     presses do nothing.
   - `CLOSE` prevents new winners while the host resolves an answer (does not clear the winner).
   - `RESET` clears the winner and stays closed — it does *not* re-open; `ARM` is required to open
     the next chance explicitly.
   - `STATUS` returns current authoritative state.
4. **Ack + state on everything.** Every accepted command gets an ack + authoritative state.
   Physical control-box actions and connect/reconnect also produce a state push (Beventra must
   never be left assuming stale state). Each `ARM` gets a unique arm number; `BUZZ` echoes it so a
   repeated or late line can't double-score.
5. **No silent auto-reopen.** Autoreset (`user_cfg.reset_duration`) must be disabled/bypassed in
   this mode — nothing should open a new chance while Beventra is waiting on the host's right/wrong
   call. Keep a usable standalone mode (current physical-control-box behavior) when no host is
   connected, and make the two modes' physical-button behavior well-defined and visibly reported
   (e.g. over `STATUS`) — don't let it silently guess which mode it's in.

Illustrative shape (exact field names/framing — JSON-lines vs space-delimited, etc. — are an
implementation decision, not fixed by this doc):

```text
Host -> Kitsune: ARM 42 A1,A2,A3,A4,A5,B1
Kitsune -> Host: STATE 42 ARMED
Kitsune -> Host: BUZZ 42 A2
Kitsune -> Host: STATE 42 LOCKED A2
Host -> Kitsune: RESET 42
Kitsune -> Host: STATE 42 CLOSED
```

The board has 10 physical ports; a given event/game may only use 6. The eligible-player mask must
be able to represent all 10 ports even when only a subset is armed.

## Explicitly out of scope here

Custom handhelds/LEDs, a new controller/enclosure, controller-mounted team lamps/screens, Wi-Fi
arbitration, a Pi/Pico hardware swap, or moving scoring logic into this firmware. Team
identity, scoring, and the right/wrong decision belong to Beventra, not this device.

## Verifying changes

There's no host-side simulator for this — verification needs the physical board connected over
USB serial. At minimum before calling protocol work done:

- Two-handheld test: rapid near-simultaneous presses resolve to exactly one winner, repeatedly.
- Confirm `CLOSE`/`RESET`/re-`ARM` sequencing matches the state machine above, including that
  `RESET` does not silently reopen.
- Unplug/replug USB mid-session; confirm `STATUS` on reconnect reflects real state and a late/stale
  `BUZZ` from before the reconnect can't score.
- Confirm standalone (no host connected) behavior still works via the physical control box.

## License / upstream

This repo is under a modified Commons Clause (see `LICENSE`): free to fork/modify/use, not to
resell. The upstream README has a standing TODO ("implement USB device identity, to work with
buzzin.live etc") that's directly adjacent to this work — once the protocol is proven against real
hardware, consider opening an upstream PR or issue rather than letting this drift as a silent fork.
