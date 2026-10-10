import machine
import switchboard
import utime
from factory import init_hardware, init_ctrl
from engine import kitsune_engine, player_box
from hostlink import usb_link
from pinouts import board_pins, firmware_version
import os
import micropython
import gc

gc.enable()
micropython.alloc_emergency_exception_buf(256)

e = None
link = None

status_led = machine.Pin(switchboard.status_pin, machine.Pin.OUT)

def status_toggle(_):
    status_led.toggle()

status_timer = machine.Timer(-1)
status_timer.init(period=500, mode=machine.Timer.PERIODIC, callback=status_toggle)



try:

    # 1. Setup

    # status LED toggle - if it's flashing, we are alive
    

    player_data, switches, mcp = init_hardware() # shim pins, read switches, init mcp

    control_button, control_led = init_ctrl(mcp)


    cfg = switchboard.runtime_config(switches) # setup runtime config with user_cfg data and switch states
    engine = kitsune_engine(cfg, control_led) # init engine with runtime config


    link = usb_link(engine) # host commands over USB serial; idle until the host sends HELLO

    players = [player_box(id=p['id'], button_obj=p['btn'], led_obj=p['led'], engine=engine, irq=True) for p in player_data]


    print(os.uname()) # type: ignore #linter is wrong

    print("Kitsune Version:", firmware_version)

    print ("Pinout:", board_pins["name"])



    engine.buzz_startup()


    # do debug
    if cfg.debug:
        print("DEBUG MODE ENABLED")

        
        try:
            for i in players:
                i.button.irq(handler=None)
            tick = 0
            while True:
                on_list = []
                off_list = []
                for p in players:
                    if p.button.value() == 1:
                        on_list.append(p.id)
                        p.update_led(1)
                    else:
                        off_list.append(p.id)
                        p.update_led(0)
                if control_button.value() == 1:
                    on_list.append("CTRL")
                    control_led.on()
                else:
                    off_list.append("CTRL")
                    control_led.off()

                for s in switches:
                    if s.value(pullup=True) == 1:
                        on_list.append(f"Switch {switches.index(s)+1}")
                    else:
                        off_list.append(f"Switch {switches.index(s)+1}")
                memfree = "{:^10}".format(gc.mem_free())
                tickform = '{:^10}'.format(str(tick))
                print(f"ON: {on_list}, OFF: {off_list}, TICK: {tickform}, MEM: {memfree}", end="\r")
                tick += 1
                #sys.stdout.flush()
                #print(f"OFF: {off_list}")
                #utime.sleep(0.1)
            #clear_line(2)

        except Exception as e:
            print(str(e))

    print("Unlock to start")


#cfg.buzzer.deinit()
#cfg.buzzer_pin.high()
# 2. Main Loop
    ctrl_was_down = False
    ctrl_last_ms = 0
    while True:
        link.poll()
        # If the MCP is used for buttons, we poll them here
        # If using IRQs on native pins, this loop stays nearly empty!
        ctrl_down = control_button.value() == 1
        # Act once per press (rising edge, 50 ms bounce guard): a held button must not
        # re-run reset every loop pass, which floods a hosted link with STATE lines.
        if ctrl_down and not ctrl_was_down and engine.locked:
            now = utime.ticks_ms()
            if utime.ticks_diff(now, ctrl_last_ms) > 50:
                ctrl_last_ms = now
                gc.collect()
                engine.reset()
        ctrl_was_down = ctrl_down

except Exception as e:
    #cfg.buzzer.duty_u16(0)
    print(str(e))
    #sys.print_exception(e)
    #machine.reset()
finally:
    if link: link.close() # never leave Ctrl-C disabled if the script stops