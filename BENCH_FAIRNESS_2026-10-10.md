# Fairness bench test, 2026-10-10

Question: does the Kitsune++ board favour one player jack over another when two players press at nearly the same time?

## Method

`Tools/edge_timing.py` runs on the board (via `mpremote run`, which pauses the buzzer firmware) and records the first rising edge on GPIO 9 (jack A4) and GPIO 14 (jack B4) with `time.ticks_us()`. For each try it prints which jack went first and the gap in microseconds. One person pressed both buttons at once, 25 tries per run, board: Kitsune++ v1.1.0, MicroPython 1.27. This measures the physical presses at the pins, independent of the game firmware.

## Results

| Run | Setup | A4 jack first | B4 jack first | Mean gap, + = A4 earlier (ms) | Median (ms) |
|---|---|---|---|---|---|
| 1 | Original hands, boxes in original jacks | 21 | 4 | +12.0 (se 2.3) | +9.4 |
| 2 | Hands swapped, boxes in original jacks | 7 | 18 | -4.2 (se 1.8) | -2.3 |
| 3 | Hands as in run 2, boxes swapped between jacks | 0 | 25 | -9.8 (se 0.9) | -8.9 |

## Reading

- **Hand effect, about 8 ms.** Swapping which hand held which box moved the lead with the hand (run 1 to run 2). Largest effect by far.
- **Box effect, about 3 ms.** Swapping the cables between jacks with the same hands (run 2 to run 3) moved the lead by 5.6 ms, i.e. the box that started in A4 fires slightly earlier than the other. Small, and near the noise.
- **Jack effect, about 1 ms (none).** The two inputs are identical GPIOs with the same pull-down; the data agree.
- The board stamps edges in microseconds, so these millisecond gaps are real differences in the presses, not board latency.

## Limits (read before quoting this)

- One person, human presses, 25 tries per run. Runs were not randomised, so order and fatigue effects are possible.
- This shows no jack bias at the millisecond level. It does not show how the firmware breaks a tie between presses under about 1 ms (the closest gap seen was 0.7 ms), and it did not test all ten jacks, only A4 and B4.
- It tests the inputs, not the game firmware's winner selection; the separate 20-try race test (11 A4, 9 B4) saw exactly one winner each time.

## Raw data

Signed gap in microseconds per try (positive = A4 jack first), in try order.

- Run 1: 8019, 11930, 17232, -1303, -2006, 1285, 8155, 3088, -2647, 9611, 27305, 18036, 26899, 20817, 27070, 26337, 43550, 19246, 7337, 1237, -694, 9953, 2404, 8441, 9372
- Run 2: -20808, 11969, -5577, -5699, -907, -4899, -2318, 3881, -1050, 1923, 8079, -715, 8071, -9511, 5884, -4536, 336, -18817, -6268, -504, -16224, -12159, -21760, -1949, -12619
- Run 3: -13721, -6059, -9654, -970, -12474, -8031, -7540, -6115, -7782, -4355, -6212, -7991, -12245, -8466, -11775, -20407, -9237, -8894, -13159, -6444, -16838, -10843, -10462, -17265, -8605
