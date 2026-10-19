import re

from hypothesis import given
from hypothesis import strategies as st

from apps.delivery.codes import (
    LOCKED,
    MALFORMED,
    MAX_ATTEMPTS,
    OK,
    WRONG,
    CodeState,
    check_code,
    generate_code,
    hash_code,
    issue_code,
)

KEY = b"test-key-not-a-real-secret"
ORDER = 42


def wrong_code(real):
    return "000000" if real != "000000" else "111111"


def test_a_code_is_six_digits_and_may_start_with_zero():
    codes = {generate_code() for _ in range(2000)}
    assert all(re.fullmatch(r"[0-9]{6}", c) for c in codes)
    assert any(c.startswith("0") for c in codes)  # leading zeros are kept


def test_the_right_code_is_accepted_and_only_a_hash_is_stored():
    code, state = issue_code(order_id=ORDER, key=KEY)
    assert code not in state.code_hash and code not in repr(state)
    new_state, result = check_code(state, code, order_id=ORDER, key=KEY)
    assert result == OK and new_state.failed_attempts == 0


def test_spaces_around_or_inside_the_code_are_ignored():
    code, state = issue_code(order_id=ORDER, key=KEY)
    spaced = f" {code[:3]} {code[3:]} "
    assert check_code(state, spaced, order_id=ORDER, key=KEY)[1] == OK


def test_a_wrong_code_uses_an_attempt():
    code, state = issue_code(order_id=ORDER, key=KEY)
    new_state, result = check_code(state, wrong_code(code), order_id=ORDER, key=KEY)
    assert (result, new_state.failed_attempts, new_state.locked) == (WRONG, 1, False)


def test_five_wrong_attempts_lock_the_code_even_against_the_right_one():
    code, state = issue_code(order_id=ORDER, key=KEY)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        state, result = check_code(state, wrong_code(code), order_id=ORDER, key=KEY)
        assert result == WRONG and state.failed_attempts == attempt
    assert state.locked
    state, result = check_code(state, code, order_id=ORDER, key=KEY)
    assert result == LOCKED  # the correct code no longer works


def test_four_wrong_attempts_do_not_lock():
    code, state = issue_code(order_id=ORDER, key=KEY)
    for _ in range(MAX_ATTEMPTS - 1):
        state, _ = check_code(state, wrong_code(code), order_id=ORDER, key=KEY)
    assert not state.locked
    assert check_code(state, code, order_id=ORDER, key=KEY)[1] == OK


def test_input_that_is_not_six_digits_does_not_use_an_attempt():
    code, state = issue_code(order_id=ORDER, key=KEY)
    for junk in ("", "12345", "1234567", "12345a", "abcdef", "１２３４５６", "12-345"):
        new_state, result = check_code(state, junk, order_id=ORDER, key=KEY)
        assert result == MALFORMED and new_state == state


def test_a_code_belongs_to_one_order_and_one_key():
    code, state = issue_code(order_id=ORDER, key=KEY)
    assert check_code(state, code, order_id=ORDER + 1, key=KEY)[1] == WRONG
    assert check_code(state, code, order_id=ORDER, key=b"another key")[1] == WRONG
    assert hash_code(code, order_id=1, key=KEY) != hash_code(code, order_id=2, key=KEY)


def test_state_repr_hides_the_hash():
    state = CodeState(code_hash="deadbeef" * 8)
    assert "deadbeef" not in repr(state)


@given(guess=st.integers(min_value=0, max_value=999_999))
def test_only_the_real_code_ever_succeeds(guess):
    state = CodeState(code_hash=hash_code("123456", order_id=ORDER, key=KEY))
    _, result = check_code(state, f"{guess:06d}", order_id=ORDER, key=KEY)
    assert (result == OK) == (guess == 123456)
