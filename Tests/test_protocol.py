import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Firmware"))

from protocol import Arbiter, ProtocolError, parse_command  # noqa: E402

IDS = ["A1", "A2", "A3", "A4", "A5", "B5", "B4", "B3", "B2", "B1"]


def hosted():
    a = Arbiter(IDS)
    a.handle_line("HELLO 1")
    return a


def armed(arm=1, ids="A1,A2,B1"):
    a = hosted()
    a.handle_line("ARM %d %s" % (arm, ids))
    return a


# --- parsing ---

def test_parse_arm_uppercases_and_splits():
    assert parse_command("arm 42 a1,b2") == ("ARM", [42, ["A1", "B2"]])


@pytest.mark.parametrize("line", [
    "HELLO", "HELLO x", "HELLO 1 2", "ARM", "ARM 1", "ARM x A1", "ARM 0 A1",
    "ARM 1 A1,,A2", "ARM 1 A1 A2", "CLOSE 1 2", "RESET x", "STATUS 1", "BYE now",
    "ARM -3 A1",
])
def test_parse_syntax_errors(line):
    with pytest.raises(ProtocolError) as e:
        parse_command(line)
    assert e.value.code == "SYNTAX"


def test_parse_unknown_and_empty():
    with pytest.raises(ProtocolError) as e:
        parse_command("FIRE")
    assert e.value.code == "UNKNOWN"
    with pytest.raises(ProtocolError) as e:
        parse_command("   ")
    assert e.value.code == "EMPTY"


def test_optional_arm_on_close_reset():
    assert parse_command("CLOSE") == ("CLOSE", [])
    assert parse_command("RESET 7") == ("RESET", [7])


def test_empty_line_is_silent():
    assert hosted().handle_line("") == []


# --- handshake / modes ---

def test_starts_standalone_and_rejects_commands():
    a = Arbiter(IDS)
    assert a.handle_line("ARM 1 A1") == ["ERR NOHOST", "STATE 0 STANDALONE"]
    assert a.handle_line("STATUS") == ["ERR NOHOST", "STATE 0 STANDALONE"]


def test_hello_enters_closed():
    a = Arbiter(IDS)
    assert a.handle_line("HELLO 1") == ["OK HELLO 1", "STATE 0 CLOSED"]


def test_hello_wrong_version():
    a = Arbiter(IDS)
    assert a.handle_line("HELLO 2") == ["ERR VERSION", "STATE 0 STANDALONE"]


def test_repeat_hello_keeps_state():
    a = armed(5, "A1")
    assert a.handle_line("HELLO 1") == ["OK HELLO 1", "STATE 5 ARMED A1"]


def test_bye_returns_to_standalone_and_clears():
    a = armed()
    a.press("A1")
    assert a.handle_line("BYE") == ["OK BYE", "STATE 1 STANDALONE"]
    assert a.winner is None


# --- ARM ---

def test_arm_reports_mask_in_port_order():
    a = hosted()
    assert a.handle_line("ARM 3 B1,A2,A1") == ["OK ARM 3", "STATE 3 ARMED A1,A2,B1"]


def test_arm_supports_all_ten_ports():
    a = hosted()
    a.handle_line("ARM 1 " + ",".join(IDS))
    assert a.mask == IDS


def test_arm_bad_id_changes_nothing():
    a = hosted()
    assert a.handle_line("ARM 1 A1,Z9") == ["ERR BADID", "STATE 0 CLOSED"]
    assert a.mode == "CLOSED"


def test_arm_numbers_must_increase():
    a = armed(5)
    assert a.handle_line("ARM 5 A1")[0] == "ERR STALE"
    assert a.handle_line("ARM 4 A1")[0] == "ERR STALE"
    assert a.handle_line("ARM 6 A1")[0] == "OK ARM 6"


def test_arm_clears_previous_winner():
    a = armed(1)
    a.press("A1")
    a.handle_line("ARM 2 A2")
    assert a.winner is None
    assert a.state_line() == "STATE 2 ARMED A2"


# --- arbitration ---

def test_first_press_wins_and_emits_buzz_then_state():
    a = armed(42)
    won, lines = a.press("A2")
    assert won
    assert lines == ["BUZZ 42 A2", "STATE 42 LOCKED A2"]
    assert a.winner == "A2"


def test_second_press_ignored():
    a = armed()
    a.press("A1")
    assert a.press("A2") == (False, [])
    assert a.winner == "A1"


def test_press_outside_mask_ignored_and_does_not_lock():
    a = armed(1, "A1")
    assert a.press("B1") == (False, [])
    assert a.mode == "ARMED"
    assert a.press("A1")[0]


def test_press_when_closed_ignored():
    a = hosted()
    assert a.press("A1") == (False, [])


def test_unknown_port_ignored():
    a = armed()
    assert a.press("Z9") == (False, [])


# --- CLOSE / RESET ---

def test_close_stops_new_winners():
    a = armed()
    assert a.handle_line("CLOSE") == ["OK CLOSE", "STATE 1 CLOSED"]
    assert a.press("A1") == (False, [])


def test_close_keeps_winner():
    a = armed()
    a.press("A1")
    assert a.handle_line("CLOSE 1") == ["OK CLOSE", "STATE 1 LOCKED A1"]
    assert a.winner == "A1"


def test_reset_clears_winner_and_stays_closed():
    a = armed(42)
    a.press("A2")
    assert a.handle_line("RESET 42") == ["OK RESET", "STATE 42 CLOSED"]
    assert a.winner is None
    assert a.press("A1") == (False, [])  # not silently reopened


def test_reset_then_arm_opens_again():
    a = armed(1)
    a.press("A1")
    a.handle_line("RESET")
    a.handle_line("ARM 2 A1")
    assert a.press("A1")[0]


def test_stale_close_reset_rejected():
    a = armed(2)
    a.press("A1")
    assert a.handle_line("RESET 1") == ["ERR STALE", "STATE 2 LOCKED A1"]
    assert a.handle_line("CLOSE 3")[0] == "ERR STALE"
    assert a.winner == "A1"


def test_late_buzz_after_reset_cannot_score():
    a = armed(1)
    a.handle_line("RESET")
    assert a.press("A1") == (False, [])


# --- STATUS ---

def test_status_is_authoritative():
    a = armed(9, "A3")
    assert a.handle_line("STATUS") == ["OK STATUS", "STATE 9 ARMED A3"]
    a.press("A3")
    assert a.handle_line("STATUS") == ["OK STATUS", "STATE 9 LOCKED A3"]


# --- standalone (physical control box) ---

def test_standalone_boots_locked():
    a = Arbiter(IDS)
    assert a.press("A1") == (False, [])


def test_standalone_first_press_wins_silently():
    a = Arbiter(IDS)
    a.control_press()
    assert a.press("B3") == (True, [])
    assert a.press("A1") == (False, [])
    assert a.winner == "B3"


def test_standalone_control_press_reopens():
    a = Arbiter(IDS)
    a.control_press()
    a.press("A1")
    assert a.control_press() == []
    assert a.winner is None
    assert a.press("A2") == (True, [])


def test_bye_locks_standalone_until_control_press():
    a = armed()
    a.handle_line("BYE")
    assert a.press("A1") == (False, [])
    a.control_press()
    assert a.press("A1")[0]


# --- physical control box while hosted ---

def test_hosted_control_press_resets_closed_and_pushes_state():
    a = armed(4)
    a.press("A1")
    assert a.control_press() == ["STATE 4 CLOSED"]
    assert a.winner is None
    assert a.press("A1") == (False, [])


# --- CHECK (roll-call) [beventra-only] ---

def test_parse_check_takes_no_arguments():
    assert parse_command("check") == ("CHECK", [])
    with pytest.raises(ProtocolError) as e:
        parse_command("CHECK A1")
    assert e.value.code == "SYNTAX"


def test_check_needs_a_host():
    a = Arbiter(IDS)
    assert a.handle_line("CHECK") == ["ERR NOHOST", "STATE 0 STANDALONE"]


def test_check_starts_empty_and_keeps_the_arm_number():
    a = armed(arm=9)
    assert a.handle_line("CHECK") == ["OK CHECK", "STATE 9 CHECK"]
    assert a.mode == "CHECK"


def test_check_records_each_port_once_in_port_order_without_locking():
    a = hosted()
    a.handle_line("CHECK")
    assert a.press("B1") == (False, ["STATE 0 CHECK B1"])
    assert a.press("A2") == (False, ["STATE 0 CHECK A2,B1"])
    assert a.press("A2") == (False, [])  # a repeat press adds nothing
    assert a.press("A4") == (False, ["STATE 0 CHECK A2,A4,B1"])
    assert a.mode == "CHECK" and a.winner is None
    assert a.handle_line("STATUS") == ["OK STATUS", "STATE 0 CHECK A2,A4,B1"]


def test_check_ignores_unknown_ports():
    a = hosted()
    a.handle_line("CHECK")
    assert a.press("Z9") == (False, [])


@pytest.mark.parametrize("line,state", [
    ("RESET", "STATE 0 CLOSED"),
    ("CLOSE", "STATE 0 CLOSED"),
    ("ARM 1 A1", "STATE 1 ARMED A1"),
])
def test_check_ends_on_reset_close_or_arm(line, state):
    a = hosted()
    a.handle_line("CHECK")
    a.press("A1")
    assert a.handle_line(line)[-1] == state
    assert a.seen == []


def test_control_box_ends_check_and_pushes_state():
    a = hosted()
    a.handle_line("CHECK")
    a.press("A1")
    assert a.control_press() == ["STATE 0 CLOSED"]
    assert a.seen == []


def test_repeat_check_starts_a_fresh_roll_call():
    a = hosted()
    a.handle_line("CHECK")
    a.press("A1")
    assert a.handle_line("CHECK") == ["OK CHECK", "STATE 0 CHECK"]
    assert a.seen == []


def test_bye_leaves_check():
    a = hosted()
    a.handle_line("CHECK")
    a.press("A1")
    a.handle_line("BYE")
    assert a.mode == "STANDALONE" and a.seen == []
