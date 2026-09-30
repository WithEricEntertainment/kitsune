"""Engine tests on a laptop: MicroPython-only modules are replaced with fakes.

These check the logic (ordering, LEDs, locked/reset behaviour), not timing or
real button hardware; that still needs the board.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Firmware"))


class FakeTimer:
    def __init__(self, *a, **k):
        self.callback = None

    def init(self, mode=None, period=None, callback=None):
        self.callback = callback

    ONE_SHOT = 0
    PERIODIC = 1


def _fake(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


_fake("micropython", schedule=lambda f, a: f(a))
_fake("machine", PWM=object, Pin=object, Timer=FakeTimer,
      disable_irq=lambda: 0, enable_irq=lambda s: None)
_fake("utime", ticks_ms=lambda: 0, ticks_diff=lambda a, b: a - b,
      sleep_ms=lambda ms: None, sleep=lambda s: None)
_fake("lib")
_fake("lib.buzzer_music", music=object)

from engine import kitsune_engine  # noqa: E402


class FakeLed:
    def __init__(self):
        self.lit = False

    def on(self):
        self.lit = True

    def off(self):
        self.lit = False


class FakePixel:
    def __init__(self):
        self.colour = None

    def fill(self, colour):
        self.colour = colour

    def write(self):
        pass


class FakePlayer:
    def __init__(self, pid):
        self.id = pid
        self.led = FakeLed()

    def update_led(self, state):
        self.led.lit = bool(state)


class FakeCfg:
    pixel = FakePixel()
    team_a_colour = (0, 0, 255)
    team_b_colour = (0, 255, 0)
    def_colour = (255, 0, 0)
    armed_colour = (128, 128, 128)
    team_a_freq_offset = 1.02
    team_b_freq_offset = 0.98
    autoreset = False
    reset_duration = 10000


def make(autoreset=False):
    cfg = FakeCfg()
    cfg.autoreset = autoreset
    cfg.pixel = FakePixel()
    led = FakeLed()
    events = []
    sent = []

    def emit(lines):
        events.append(("emit", list(lines)))
        sent.extend(lines)

    e = kitsune_engine(cfg, led, emit=emit)
    e.buzz = lambda *a, **k: events.append(("buzz",))
    players = {p: FakePlayer(p) for p in ["A1", "A2", "B1"]}
    return e, players, led, events, sent, cfg


def finish_refractory(e):
    e.reset_refractory(None)


# --- standalone: behaves as before the protocol existed ---

def test_boots_locked_and_ignores_presses():
    e, p, led, events, sent, cfg = make()
    assert e.locked
    e.handle_buzz(p["A1"])
    assert e.active_player is None
    assert not p["A1"].led.lit


def test_control_press_arms_then_first_press_wins():
    e, p, led, events, sent, cfg = make()
    e.reset()
    finish_refractory(e)
    assert not e.locked and led.lit
    assert cfg.pixel.colour == cfg.armed_colour

    e.handle_buzz(p["A2"])
    assert e.locked
    assert e.active_player is p["A2"] and p["A2"].led.lit
    assert not led.lit
    assert cfg.pixel.colour == cfg.team_a_colour
    assert ("buzz",) in events

    e.handle_buzz(p["B1"])  # second press does nothing
    assert e.active_player is p["A2"] and not p["B1"].led.lit
    assert sent == []  # nothing is sent with no host


def test_standalone_reset_clears_winner_led():
    e, p, led, events, sent, cfg = make()
    e.reset()
    finish_refractory(e)
    e.handle_buzz(p["A1"])
    e.reset()
    assert e.active_player is None and not p["A1"].led.lit
    assert not e.locked


def test_press_during_refractory_ignored():
    e, p, led, events, sent, cfg = make()
    e.reset()  # refractory not yet cleared
    e.handle_buzz(p["A1"])
    assert e.active_player is None


def test_autoreset_runs_standalone():
    e, p, led, events, sent, cfg = make(autoreset=True)
    e.reset()
    finish_refractory(e)
    e.handle_buzz(p["A1"])
    assert e.locked
    e._autoreset(None)
    assert not e.locked


# --- hosted ---

def host(e):
    e.handle_command("HELLO 1")


def test_host_buzz_emitted_before_sound():
    e, p, led, events, sent, cfg = make()
    host(e)
    e.handle_command("ARM 7 A1,A2")
    events.clear()
    e.handle_buzz(p["A2"])
    assert events[0] == ("emit", ["BUZZ 7 A2", "STATE 7 LOCKED A2"])
    assert events[1] == ("buzz",)
    assert p["A2"].led.lit


def test_host_ineligible_press_does_nothing():
    e, p, led, events, sent, cfg = make()
    host(e)
    e.handle_command("ARM 1 A1")
    events.clear()
    e.handle_buzz(p["B1"])
    assert events == [] and not p["B1"].led.lit
    assert not e.locked  # still armed for A1


def test_host_arm_lights_control_and_clears_old_winner_led():
    e, p, led, events, sent, cfg = make()
    host(e)
    e.handle_command("ARM 1 A1,A2")
    assert led.lit
    e.handle_buzz(p["A1"])
    assert p["A1"].led.lit and not led.lit
    e.handle_command("ARM 2 A1,A2")
    assert not p["A1"].led.lit and led.lit


def test_host_reset_clears_led_and_stays_closed():
    e, p, led, events, sent, cfg = make()
    host(e)
    e.handle_command("ARM 1 A1")
    e.handle_buzz(p["A1"])
    del sent[:]
    e.handle_command("RESET 1")
    assert sent == ["OK RESET", "STATE 1 CLOSED"]
    assert not p["A1"].led.lit and not led.lit
    assert e.locked  # closed: main loop keeps watching the control box
    e.handle_buzz(p["A1"])
    assert not p["A1"].led.lit


def test_host_close_keeps_winner_lit():
    e, p, led, events, sent, cfg = make()
    host(e)
    e.handle_command("ARM 1 A1")
    e.handle_buzz(p["A1"])
    e.handle_command("CLOSE")
    assert p["A1"].led.lit and e.active_player is p["A1"]


def test_control_box_while_hosted_resets_and_pushes_state():
    e, p, led, events, sent, cfg = make()
    host(e)
    e.handle_command("ARM 3 A1")
    e.handle_buzz(p["A1"])
    del sent[:]
    e.reset()
    assert sent == ["STATE 3 CLOSED"]
    assert not p["A1"].led.lit


def test_no_autoreset_when_hosted():
    e, p, led, events, sent, cfg = make(autoreset=True)
    host(e)
    e.handle_command("ARM 1 A1")
    e.handle_buzz(p["A1"])
    e.handle_command("STATUS")
    e._autoreset(None)  # even if a stale timer fires
    assert e.arbiter.winner == "A1"
    assert e.locked


def test_bye_returns_to_locked_standalone():
    e, p, led, events, sent, cfg = make()
    host(e)
    e.handle_command("ARM 1 A1")
    e.handle_command("BYE")
    assert e.locked
    e.reset()
    finish_refractory(e)
    e.handle_buzz(p["A1"])
    assert e.active_player is p["A1"]
