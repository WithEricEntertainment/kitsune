#note: refining using Gemini https://gemini.google.com/app/39fc3339e3460a7a



import micropython
from machine import PWM, Pin, Timer, disable_irq, enable_irq
import utime
from lib.buzzer_music import music
from pinouts import board_pins
from protocol import Arbiter, STANDALONE, ARMED, CHECK


class player_box():
    """Non-controller boxes. Passes button presses to game engine."""
    def __init__(self, engine, button_obj, handler=None, led_obj=None, id="",  irq=False):

        self.button = button_obj
        self.engine = engine
        self.id = id
        self._debounce_ms = 10
        self.last_press_time = 0

        if irq: #and not hardware_cfg.game.debug:
            self.button.irq(handler=self._handle_press, trigger=self.button.IRQ_RISING)



        # update_led() reads self.led, so it must exist even when no LED was passed in
        self.led = led_obj
        
        

    def update_led(self, state):
        if self.led is not None:
            if state:
                self.led.on()
            else:
                self.led.off()
        


    def _handle_press(self, _):

        # get current time
        current_time = utime.ticks_ms()

        # check that time since last press is greater than debounce time, or that time has wrapped
        self.period = utime.ticks_diff(current_time, self.last_press_time)
        if self.period > self._debounce_ms or self.period < 0:
            self.last_press_time = current_time
            micropython.schedule(self.engine.handle_buzz, self)








class kitsune_engine():



    def __init__(self, cfg, control_led, emit=None):
        self.cfg = cfg
        self.arbiter = Arbiter(board_pins["ids"])
        self.emit = emit or (lambda lines: None)  # sends protocol lines to the host
        self.active_player = None
        self.check_lit = {}  # CHECK roll-call: port id -> player whose LED is held on
        self.refractory = False
        self.ref_timer = Timer(-1)
        self.control_led = control_led
        self.team_offset = 1 # frequency coefficient to vary buzz sound by team
        print("Init engine")

    @property
    def locked(self):
        """True whenever a button press cannot win (main loop polls this to watch for reset)."""
        a = self.arbiter
        return not (a.open if a.mode == STANDALONE else a.mode == ARMED)

    def handle_buzz(self, player):
        if self.refractory: return

        # Lock and record the winner first; nothing slow happens before this.
        won, lines = self.arbiter.press(player.id)
        if self.arbiter.mode == CHECK:
            # Roll-call: light the box and keep it lit, tell the host, make no sound.
            if lines:
                self.check_lit[player.id] = player
                player.update_led(1)
                self.emit(lines)
            return
        if not won: return

        self.active_player = player
        player.update_led(1)
        self.emit(lines) # tell the host before the ~625ms buzz below
        self.control_led.off()

        if "A" in player.id:
            self.cfg.pixel.fill(self.cfg.team_a_colour)
            self.team_offset = self.cfg.team_a_freq_offset
        elif "B" in player.id:
            self.cfg.pixel.fill(self.cfg.team_b_colour)
            self.team_offset = self.cfg.team_b_freq_offset
        else:
            self.cfg.pixel.fill(self.cfg.def_colour)
            self.team_offset = 1
        self.cfg.pixel.write()

        print(f"Buzzer locked by {player.id}")
        self.buzz(self.cfg)
        # Autoreset only makes sense with no host; a host must never see a silent reopen.
        if self.cfg.autoreset and self.arbiter.mode == STANDALONE:
            Timer(-1).init(mode=Timer.ONE_SHOT, period=self.cfg.reset_duration, callback=self._autoreset)

    def _autoreset(self, _):
        if self.arbiter.mode == STANDALONE: # a host may have connected since the timer started
            self.reset()

    def reset(self, *args):
        """Control-box reset. Standalone: reopen. Hosted: clear winner and stay closed."""
        lines = self.arbiter.control_press()
        self._sync_outputs()
        self.emit(lines)

    def handle_command(self, line):
        """One host command line in; state applied to the hardware, reply lines out."""
        lines = self.arbiter.handle_line(line)
        self._sync_outputs()
        self.emit(lines)

    def _sync_outputs(self):
        """Make LEDs match the arbiter. Winner-lighting is done in handle_buzz."""
        a = self.arbiter
        keep = a.seen if a.mode == CHECK else []
        for pid in list(self.check_lit):
            if pid not in keep:  # left CHECK, or a fresh roll-call started
                self.check_lit.pop(pid).update_led(0)
        if a.winner is None and self.active_player:
            self.active_player.update_led(0)
            self.active_player = None
        if a.winner is not None:
            return
        armed = a.open if a.mode == STANDALONE else a.mode == ARMED
        self.cfg.pixel.fill(self.cfg.armed_colour if armed else (0, 0, 0))
        self.cfg.pixel.write()
        if armed:
            self.control_led.on()
        else:
            self.control_led.off()

        if armed and a.mode == STANDALONE:
            # Brief debounce so the press that reset us can't also win.
            self.refractory = True
            self.ref_timer.init(mode=Timer.ONE_SHOT, period=20, callback=self.reset_refractory)

    def reset_refractory(self, _):
        self.refractory = False
        print("cleared refractory period")



    def buzz(self, config=None):
        """
        Buzz the speaker with the given configuration.

        Args:
            config (runtime_config): The runtime configuration object.
        """
        if config is None:
            config = self.cfg
        speaker = PWM(config.buzzer_pin, freq=2500, duty_u16=0)
        #speaker.duty_u16(50000)
        volume = round(config.volume)
        freqmod = (config.freqmod/100) * self.team_offset
        print(f"Buzzing at volume {volume} and freqmod {freqmod}")
        if not config.mute:


            print("Start buzz")
            speaker.duty_u16(volume)
            speaker.freq(round(900*freqmod))

            speaker.freq(round(300*freqmod))
            utime.sleep_ms(125)

            speaker.duty_u16(0)
            utime.sleep_ms(25)
            speaker.duty_u16(volume)

            speaker.freq(round(750*freqmod))
            utime.sleep_ms(125)
            
            speaker.duty_u16(0)
            utime.sleep_ms(25)
            speaker.duty_u16(volume)
            
            speaker.freq(round(300*freqmod))
            utime.sleep_ms(125)
            
            speaker.duty_u16(0)
            utime.sleep_ms(25)
            speaker.duty_u16(volume)

            speaker.freq(round(750*freqmod))
            utime.sleep_ms(125)
            
            speaker.duty_u16(0)
            utime.sleep_ms(25)
            speaker.duty_u16(volume)

            speaker.freq(round(300*freqmod))
            utime.sleep_ms(125)

            speaker.duty_u16(0)
            speaker.deinit()
            print("End buzz")
        return()
    
    def buzz_startup(self):
        """
        Buzz the speaker with the given configuration.

        Args:
            config (runtime_config): The runtime configuration object.
        """
        volume = round(self.cfg.volume)
        print(f"Startup Buzzing at volume {volume}")

        jingletrack = "0 G5 1 15 0.5039370059967041;1 F#5 1 15 0.5039370059967041;3 E5 3 15 0.5039370059967041;6 F#5 2 15 0.5039370059967041"
        jingler = Pin(board_pins["buzzer_pin"])
        jingle = music(jingletrack, pin=jingler, looping=False, duty=volume)

        if not self.cfg.mute:
            print("Start startup buzz")
            while True:
                jingle.tick()
                utime.sleep(0.04)
                if jingle.stopped:
                    jingle.stop()
                    break
            print("End startup buzz")
        PWM(jingler).deinit()

        return()