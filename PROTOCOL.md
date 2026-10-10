# Kitsune USB serial protocol (version 1)

A small line-based text protocol that lets a computer arm, close and reset the buzzers over the
USB serial port and be told who buzzed in first. The buzzer box decides the winner itself; the
host never sits in the decision path.

The reference implementation is `Firmware/protocol.py` (parsing and state) and
`Firmware/hostlink.py` (serial I/O). Tests are in `Tests/`. **Status: unit-tested under CPython
(regular Python on a computer) and verified on a real Kitsune++ v1.1.0 on 2026-10-10; see the end of this file.**

## Connecting

Use the USB-C port on the Pico module itself (the middle one of the three on the board's edge),
which appears as a normal USB serial device. The two outer USB-C sockets are UART daisychain
sockets and are not used here.

The firmware also prints ordinary diagnostics on the same stream. Every protocol line from the
device starts with `KIT `; **the host must ignore any line that doesn't**.

## Framing

- One message per line, ended by `\n` (a `\r` before it is ignored).
- Space-separated fields. Command names and player IDs are case-insensitive on input.
- Input lines longer than 96 characters are rejected with `ERR TOOLONG`.
- Arm numbers are positive integers chosen by the host.
- Player IDs are the board's ports: `A1`-`A5`, `B1`-`B5`. Any subset of the ten can be armed.

## Modes

| Mode | Meaning |
|---|---|
| `STANDALONE` | No host. The physical control box works as it always has: the unit boots locked, a control press opens it, the first buzz wins and locks it, a control press resets. Only `HELLO`/`BYE` are accepted. |
| `CLOSED` | Host connected, nobody can win. |
| `ARMED` | Host connected; only the listed players can win. |
| `LOCKED` | Host connected; a winner is held until `RESET` or the next `ARM`. |

## Host to device

| Command | Effect |
|---|---|
| `HELLO 1` | Enter host mode (version must be 1, else `ERR VERSION`). From standalone this goes to `CLOSED`. Sent again while already hosted (e.g. after a reconnect) it changes nothing and just reports the current state. Disables Ctrl-C on the serial port. |
| `ARM <arm> <ids>` | Clear any winner and allow only the listed players (comma-separated, e.g. `A1,A2,B1`) to win. `<arm>` must be greater than every previous arm number (`ERR STALE` otherwise). An unknown ID gives `ERR BADID` and changes nothing. Allowed from any hosted state. |
| `CLOSE [<arm>]` | Stop new winners. An existing winner is kept (`LOCKED` stays `LOCKED`). |
| `RESET [<arm>]` | Clear the winner and go to `CLOSED`. It never reopens; `ARM` is required for that. |
| `STATUS` | Report the current state. |
| `BYE` | Leave host mode: back to `STANDALONE`, locked until the control box opens it, and Ctrl-C is restored. |

If `<arm>` is given to `CLOSE`/`RESET` and isn't the current arm, the command is refused with
`ERR STALE`.

## Device to host (all lines start with `KIT `)

| Line | Meaning |
|---|---|
| `OK <command> ...` | The command was accepted: `OK HELLO 1`, `OK ARM 42`, `OK CLOSE`, `OK RESET`, `OK STATUS`, `OK BYE`. Always followed by a `STATE` line. |
| `STATE <arm> STANDALONE` or `CLOSED` | Current mode. `<arm>` is the latest arm number (0 before any). |
| `STATE <arm> ARMED <ids>` | Armed, with the eligible players in port order. |
| `STATE <arm> LOCKED <id>` | Locked with this winner. |
| `BUZZ <arm> <id>` | A player won. Sent as soon as the winner is locked, *before* the buzzer sound plays, and always followed by `STATE <arm> LOCKED <id>`. |
| `ERR <code>` | The command was refused. |

Error codes: `SYNTAX` (malformed), `UNKNOWN` (no such command), `TOOLONG`, `VERSION`, `NOHOST`
(command needs `HELLO` first), `STALE` (old or repeated arm number), `BADID`. After `VERSION`,
`NOHOST`, `STALE` and `BADID` the device also sends a `STATE` line so the host can resync;
`SYNTAX`, `UNKNOWN` and `TOOLONG` are sent alone. Blank lines are ignored silently.

State is also pushed without being asked when the physical control box is pressed while a host is
connected. It acts like `RESET` (clears the winner, stays `CLOSED`) and sends `STATE <arm> CLOSED`.
While `ARMED`, the control box does nothing.

## Example

```text
host   HELLO 1
device KIT OK HELLO 1
device KIT STATE 0 CLOSED
host   ARM 42 A1,A2,B1
device KIT OK ARM 42
device KIT STATE 42 ARMED A1,A2,B1
        ... A2 presses first ...
device KIT BUZZ 42 A2
device KIT STATE 42 LOCKED A2
host   RESET 42
device KIT OK RESET
device KIT STATE 42 CLOSED
```

## Guidance for hosts

- **Trust the arm number.** Ignore any `BUZZ` whose arm isn't the one you last armed; that stops a
  late or repeated line from scoring twice.
- **Reconnecting:** the device can't tell that the cable was unplugged, so it stays in host mode
  with its state intact. After reconnecting, send `HELLO 1` and read the `STATE` line before
  doing anything else. Choose the next arm number above the one it reports. A device that
  rebooted reports arm 0.
- **Autoreset is ignored** while a host is connected; nothing reopens on its own timer.
- **Sound delay:** the buzzer sound takes about 625 ms and commands sent during it wait in the
  serial buffer. The `BUZZ` line is not delayed by it.
- **Ctrl-C is off** between `HELLO` and `BYE`, so a running script can't be interrupted over
  serial. Recover with `BYE`, `mpremote reset`, or unplugging.

## Verified on hardware (2026-10-10, Kitsune++ v1.1.0, MicroPython 1.27)

Checked on a real board over its middle USB-C port:

- Every command and the error replies (`NOHOST`, `STALE`, `BADID`, `UNKNOWN`) answer as documented.
- A real button press produces `BUZZ` then `LOCKED`, and `RESET`/`CLOSE`/`BYE` return the right state.
- Reconnect: dropping the serial connection without `BYE` keeps state, and `HELLO 1` reports it. A real
  unplug and replug reboots the board to `STANDALONE`, arm 0.
- Two boxes (A4, B4), 20 near-simultaneous tries: exactly one winner each time (A4 11, B4 9), no
  errors. Human timing only; not proof of millisecond-level fairness.
- Host gone mid-round (serial closed without `BYE`, armed): a press still sounds instantly and the winner
  is held. The `BUZZ` line sent while nobody was reading is lost, but `HELLO 1` on reconnect reports
  `STATE <arm> LOCKED <id>`, so hosts must recover the winner from that, not from `BUZZ` alone.
- Standalone with nothing reading the port: no delay. One cable (middle USB-C, 27V buzzer): no resets
  or disconnects across the session.

Still open: true same-millisecond presses, weak USB chargers.

Practical notes found on the board:

- Stray bytes in the input line (e.g. Linux ModemManager probing a newly attached serial device) make
  the next command fail once with `ERR UNKNOWN`. Hosts should send a blank line before `HELLO 1`
  and ignore any line that doesn't start with `KIT `.
- `mpremote` cannot connect while the board is in host mode (Ctrl-C is off); send `BYE` or replug.
  After any `mpremote` use the board is left at the MicroPython prompt; run `mpremote reset`.
- `BYE` keeps the last arm number; only a reboot resets it to 0.
- The board's own `Firmware/pinouts.py` selects `p10v1p1_pins` (v1.1.0). The repo copy selects
  `p10v1_pins`; don't overwrite the board's with it.
