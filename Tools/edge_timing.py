# Bench tool: timestamps the first press edge on A4 (GPIO 9) and B4 (GPIO 14) and prints which went first
# and by how many microseconds. Run with: .venv/bin/mpremote connect /dev/ttyACM0 run Tools/edge_timing.py
# (pauses the buzzer firmware; run 'mpremote reset' afterwards). Results: BENCH_FAIRNESS_2026-10-10.md
from machine import Pin
import time
a = Pin(9, Pin.IN, Pin.PULL_DOWN)   # A4
b = Pin(14, Pin.IN, Pin.PULL_DOWN)  # B4
t = {}
def ha(p):
    if 'A4' not in t: t['A4'] = time.ticks_us()
def hb(p):
    if 'B4' not in t: t['B4'] = time.ticks_us()
a.irq(handler=ha, trigger=Pin.IRQ_RISING)
b.irq(handler=hb, trigger=Pin.IRQ_RISING)
print("READY")
n = 0
end = time.ticks_add(time.ticks_ms(), 150000)
while n < 25 and time.ticks_diff(end, time.ticks_ms()) > 0:
    if t:
        time.sleep_ms(300)  # let the other button arrive
        if 'A4' in t and 'B4' in t:
            d = time.ticks_diff(t['B4'], t['A4'])  # >0: A4 first
            print("ROUND", n + 1, "A4" if d > 0 else "B4", abs(d))
        else:
            print("ROUND", n + 1, "only", list(t)[0])
        n += 1
        # wait until both released, then re-arm
        while a.value() or b.value():
            time.sleep_ms(20)
        time.sleep_ms(400)
        t.clear()
print("DONE")
