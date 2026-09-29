# Beventra integration — implementation plan

This is the actual build plan, derived from `CLAUDE.md`'s spec plus the real firmware source and
one piece of external research (`micropython.kbd_intr`). `CLAUDE.md` says *what* the protocol must
do; this doc says *how* to get there in this codebase, in what order, and what's still undecided.
Read this before writing any protocol code — it's the thing to sign off on, not the source diff.

## Findings this plan is built on (not re-derived here — see CLAUDE.md for detail)

- Buttons are IRQ-driven (`player_box._handle_press`, `IRQ_RISING`) and dispatched via
  `micropython.schedule`, independent of the main loop. First-press arbitration doesn't depend on
  how fast (or slow) a new stdin-polling loop runs.
- `sys.stdin` during `main.py` execution is not competing with an active REPL prompt — the REPL
  only resumes if the script exits/crashes. The one thing that *does* intercept bytes unconditionally
  is Ctrl-C (`0x03`), and `micropython.kbd_intr(-1)` turns that off — documented for exactly this
  case ("in case that stream is used for other purposes"). This was the open question from the
  Beventra-side doc's step 1; it's resolved, not still a risk.
- `pinouts.py` defaults to the wrong pin map (`p10v1_pins`, not `p10v1p1_pins`) for this board.
- `engine.handle_buzz()` calls a ~625ms blocking buzz sequence synchronously, before any reset logic.
- **New in this pass, from rereading `main.py`/`engine.py`/`factory.py`/`switchboard.py` specifically
  for wire-cleanliness:** far more `print()` calls are unconditional than just the interactive debug
  loop — `factory.py`'s `init_mcp`/`init_hardware`/`init_ctrl`, `switchboard.py`'s
  `runtime_config.__init__` (an 8-line config dump), and `engine.py`'s `handle_buzz`/`reset`/
  `reset_refractory` all print on every boot and every buzz, none gated by `cfg.debug`. A naive
  protocol implementation that just starts parsing `sys.stdin` lines will have these interleaved on
  the same stream as `ARM`/`BUZZ`/`STATE` — this needs an explicit decision (see below), not an
  assumption that "most prints are already gated."

## Bucketing: Beventra-specific vs. core Kitsune

Standing principle for this whole effort (set 2026-09-29): don't reinvent what the upstream project
already does well, and where possible, build this as something worth giving back rather than a
silent fork. Every change gets one of two tags:

- **`[core]`** — belongs in the firmware regardless of who's driving it; would make sense in an
  upstream PR to `Amekyras/kitsune` on its own merits, not just because Beventra needs it.
- **`[beventra-only]`** — specific to this integration; stays a local diff, not upstream-worthy.

**Heavy `[core]` changes only ship if they'd genuinely benefit the upstream project on their own** —
not merely because they're the most elegant way to satisfy Beventra's spec. Where a heavier `[core]`
approach and a lighter `[beventra-only]` shortcut both solve the immediate need, default to the
lighter one unless the heavier one clears that bar.

One structural fact worth naming, stated precisely this time: **the arm → lock → reset decision
loop is not new — Kitsune already does exactly that, today, via the physical control box.** This
plan doesn't reinvent that loop; it exposes it over USB instead of only a thumb on a button, plus
three small additions the physical-button interface has no way to express:

- separating "clear the winner" (`RESET`) from "open the next chance" (`ARM`) — today one control
  button press does both, and Beventra needs a "host is still deciding right/wrong" gap between them
- restricting who's eligible to buzz to a subset of the 10 ports (`ARM`'s player-ID list) — today
  any connected port can win whenever unlocked
- a queryable/ack'd channel (`STATUS`, command acks) so a remote host can trust the state it sees,
  which a physical button obviously never needed

Because `CLAUDE.md` already keeps team identity, scoring, and the right/wrong decision entirely out
of firmware (Beventra owns all of that on the host side), none of those three additions needed to be
Beventra-shaped either — they're generic to "let any external controller drive this loop," which is
exactly the kind of thing the upstream README's own TODO ("implement USB device identity, to work
with buzzin.live etc") is asking for. Beventra is the first consumer of that capability, not a
special case baked into the wire format. Worth being honest about what that claim does and doesn't
mean, though: it's not that upstream was already about to build this unprompted — it's additive
functionality that only matters once *something* is driving it externally. The claim is narrower and
still true: nothing here bakes in a Beventra-specific assumption, so it's a plausible, welcome
contribution rather than a fork that diverges from upstream's own direction.

## Design decisions

**1. `[core]` Explicit state machine, replacing the two booleans.** `engine.locked`/`refractory` today only
distinguish "someone's buzzed" from "briefly debouncing after reset." The protocol needs to
distinguish *why* buzzing is disabled: `STANDALONE` (no host, physical control box in charge, current
behavior), `CLOSED` (host connected, no active arm), `ARMED <arm#, mask>`, `LOCKED <arm#, winner>`.
Add this as one explicit mode field on `kitsune_engine` rather than inferring it from combinations of
booleans — the doc's requirement that `STATUS`/reconnect always reflect *authoritative* state is hard
to guarantee if state is implicit.

**2. `[core]` Eligibility mask is new — there isn't one today.** `_handle_press`/`handle_buzz` currently
accept any press whenever `not (locked or refractory)`. `ARM <arm#> <ids>` needs to restrict that to
a specific set of player IDs; everyone else's press must be a no-op, not just "too late." In
`STANDALONE` mode (no host), preserve current behavior by treating the mask as "all IDs, always
armed" — this is what keeps the physical-control-box-only mode working unchanged.

**3. `[core]` Arm numbers are host-assigned, not device-generated.** Per the doc's own illustrative
exchange (`Host -> Kitsune: ARM 42 ...`), the host picks the number; the device just stores and
echoes it on `STATE`/`BUZZ` until the next `ARM`. No device-side counter needed. This also gives
the late/duplicate-line protection required by CLAUDE.md's requirement 4 "for free" on the host
side, as long as the device refuses to honor a press once it's left `ARMED` for that arm number
(i.e. mask is cleared on `CLOSE`/`RESET`, not just logically ignored).

**4. `[core]` Wire cleanliness: tag protocol lines, don't try to gate every print.** Given how many
unconditional prints exist (finding above), retrofitting `if cfg.debug:` onto every one of them is
higher-risk (easy to miss one, easy to break the existing standalone/debug UX) than making the
protocol side robust to noise. Decision: all protocol output goes through one `proto_send(line)`
helper that prefixes with a fixed token (e.g. `KIT `); the host-side parser only looks at lines
with that prefix and ignores everything else. Existing prints stay as-is. This is a smaller, more
reviewable diff and matches "keep changes minimal, plausible as an upstream PR" from CLAUDE.md.

**5. `[core]` (but explicitly the "lighter option" — see bucketing note) Don't rewrite `buzz()` as
non-blocking — reorder around it instead.** A full Timer-driven
non-blocking rewrite of the PWM sequence is more code and more risk to the audio behavior than this
integration needs. Instead: emit the `BUZZ`/`STATE LOCKED` event *immediately* on lock, before
calling `self.buzz()`. The host learns of the winner in microseconds regardless of the ~625ms audio
tail; the only cost is the device won't process an incoming command during that window, and the
protocol as specified doesn't require the host to send anything immediately after seeing `LOCKED`
(it waits for a human right/wrong call, which takes far longer than 625ms). Flag this as something
to watch during acceptance testing, not something to solve preemptively.

**6. `[core]` — resolved: keep the `HELLO`/`BYE` handshake.** `kbd_intr(-1)` should be scoped to
"host connected," not global from boot. Disabling Ctrl-C capture everywhere loses a real debugging
convenience (interrupting a runaway script over serial) for zero benefit in standalone mode.
Handshake: host sends `HELLO` to explicitly enter host-controlled mode; device acks, calls
`kbd_intr(-1)`, and only then starts treating `sys.stdin` as protocol input rather than plain
REPL/debug. On USB disconnect (detectable) or an explicit `BYE`, restore `kbd_intr(3)` and drop
back to `STANDALONE`. This clears the "is it heavy enough to justify" bar: it's a handful of lines,
it's the kind of explicit connect/disconnect semantics any external-controller integration would
want (not Beventra-specific), and it directly produces the mode visibility `STATUS` needs anyway.

**7. `[core]` `STATUS` returns the full state tuple**: mode, current arm number, eligible mask,
active winner (if any). This is what both reconnect-reconciliation and the acceptance checklist's
"unplug/replug, confirm host sees real state" step depend on.

**8. `[core]` (dev-practice, not firmware behavior — but worth giving back as tests, not just code)
Pull the protocol parser/state machine into a plain-Python module, testable off-device.**
Command parsing (`"ARM 42 A1,A2,..."` → structured command) and the state-transition logic don't
need `machine`/`utime`/hardware — write them with no MicroPython-only imports, unit-test with
ordinary `pytest` on a laptop, then import the same file unmodified on the device. This is the
part of the work that genuinely doesn't need the Pico spike or the board at all, and is where most
of the bug surface (malformed lines, wrong transitions, double-buzz edge cases) actually lives —
better to catch it in a fast local test loop than in on-device debugging.

## Sequencing

- **Phase 0 — hardware sanity, blocks on-device validation.** Once the unit arrives: plug the
  middle USB-C into the computer, confirm `mpremote` sees it, flash stock-equivalent firmware, and
  run the existing two-handheld checks (buzz/LED/control button) with *no* protocol code. (An
  earlier draft called for switching `board_pins` to `p10v1p1_pins`; the v1.0/v1.1.0 maps have
  identical pins, so this is optional and only changes the default volume.)
- **Phase 1 — offline, no hardware required, can start now (done: `feature/host-command-parser`).**
  Write the protocol parser + state machine as a standalone module, with `pytest` coverage for:
  valid `ARM`/`CLOSE`/`RESET`/`STATUS` transitions, rejected presses outside the eligible mask,
  stale-arm-number rejection, and malformed-line handling.
- **Phase 2 — wire into `engine.py`/`main.py`.** Add the `proto_send` tagging, the `HELLO`/`BYE`
  mode switch, replace the boolean state with the explicit mode field, add the eligibility mask
  check into `_handle_press`/`handle_buzz`, reorder event-emit-before-`buzz()`. Keep `STANDALONE`
  behavior unchanged and manually re-verified.
- **Phase 3 — on-device validation**, per `CLAUDE.md`'s "Verifying changes" checklist
  (near-simultaneous presses, close/reset/re-arm sequencing, USB unplug/replug, standalone
  fallback).
- **Phase 4 — Beventra host-console side** (Web Serial integration, six-slot assignment UI, etc.)
  — separate repo, tracked as Beventra's `WI-1418`, only starts once Phase 3 passes *and* Beventra's
  own `WI-1417` (the playoff UI this plugs into) exists. Not blocked on this repo's firmware work in
  the other direction — Beventra is validating the shared event-contract design in parallel via a
  keyboard-simulated POC (`WI-1419`, no dependency on this repo) rather than waiting on Phase 0-3 to
  finish first. See Beventra's `DEC-010`/`DEC-011` decision docs for the cross-repo picture.

## Open questions — resolved via the bucketing principle (2026-09-29)

- **`HELLO`/`BYE` handshake:** keep it (decision 6, above) — small, `[core]`, clears the "genuinely
  benefits the project" bar on its own.
- **Wire format:** space-delimited text, matching the doc's illustration and the project's existing
  plain-print aesthetic — not JSON. JSON parsing/encoding is unnecessary code weight on-device for
  messages this small; a heavier format isn't justified by the "only if it truly benefits" filter
  when the simple option covers the need. `[core]`.
- **Arm-number type:** plain small integers, no wraparound handling — nothing here runs long enough
  for it to matter, and building headroom for it would be exactly the kind of premature "heavy"
  change the bucketing principle says to skip. `[core]`.

No items landed in `[beventra-only]` — see the bucketing note above for why: team/score/decision
logic already lives entirely in Beventra's host console, not this firmware, so nothing in the
protocol itself needed to be special-cased for Beventra. If a genuinely Beventra-specific firmware
need turns up later (unlikely, but possible once Phase 2 implementation starts), tag it
`[beventra-only]` explicitly here rather than letting it blend into the `[core]` work.

## Still not resolvable without the physical board

Also open: whether writes to `sys.stdout` block when no host is attached (would delay the `BUZZ`
emit and the buzz sound), whether power sources on the outer USB-C sockets are safe alongside the
middle port, and that a script holding `kbd_intr(-1)` cannot be interrupted over serial (recover
with `BYE`, `mpremote reset`, or replugging).

`select.poll(sys.stdin)` behavior specifically on the `rp2` port's USB CDC driver (docs confirm the
`kbd_intr` mechanism generally but don't document rp2-specific buffering), real button-press race
timing/fairness, and Web Serial's actual handshake with this board's USB descriptor. These stay as
Phase 0/3 hardware checks, not resolved by this plan.
