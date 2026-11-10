import re

from hypothesis import given
from hypothesis import strategies as st

from apps.delivery.codes import LOCKED, MALFORMED, MAX_ATTEMPTS, OK, WRONG
from apps.delivery.derived_codes import (
    DerivedCodeState,
    check_derived,
    derive_code,
    issue_derived,
    new_nonce,
)

KEY = b"test-key-not-a-real-secret"
ORDER = 42
NONCE = "00" * 16


def wrong_code(real):
    return "000000" if real != "000000" else "111111"


def test_known_answer_so_the_derivation_never_changes_by_accident():
    # Changing this changes every code already issued. Rotate keys instead of editing this.
    assert derive_code(order_id=ORDER, nonce=NONCE, key=KEY) == "829022"


def test_the_same_inputs_always_give_the_same_code():
    assert derive_code(order_id=ORDER, nonce=NONCE, key=KEY) == derive_code(
        order_id=ORDER, nonce=NONCE, key=KEY
    )


def test_a_code_is_six_digits_and_may_start_with_zero():
    codes = {derive_code(order_id=i, nonce=NONCE, key=KEY) for i in range(3000)}
    assert all(re.fullmatch(r"[0-9]{6}", c) for c in codes)
    assert any(c.startswith("0") for c in codes)
    assert len(codes) > 2500  # spread out, not stuck on a few values


def test_order_nonce_and_key_each_change_the_code():
    base = [derive_code(order_id=ORDER, nonce=NONCE, key=KEY)]
    orders = {derive_code(order_id=i, nonce=NONCE, key=KEY) for i in range(50)}
    nonces = {derive_code(order_id=ORDER, nonce=new_nonce(), key=KEY) for _ in range(50)}
    keys = {derive_code(order_id=ORDER, nonce=NONCE, key=bytes([i]) * 8) for i in range(50)}
    assert len(orders) > 40 and len(nonces) > 40 and len(keys) > 40 and base


def test_the_issued_code_checks_out_and_the_state_holds_no_code():
    code, state = issue_derived(order_id=ORDER, key=KEY)
    assert code not in repr(state) and state.nonce not in repr(state)
    new_state, result = check_derived(state, code, order_id=ORDER, key=KEY)
    assert result == OK and new_state.failed_attempts == 0


def test_the_code_can_be_shown_again_from_the_stored_state():
    code, state = issue_derived(order_id=ORDER, key=KEY)
    assert derive_code(order_id=ORDER, nonce=state.nonce, key=KEY) == code


def test_spaces_around_or_inside_the_code_are_ignored():
    code, state = issue_derived(order_id=ORDER, key=KEY)
    assert check_derived(state, f" {code[:3]} {code[3:]} ", order_id=ORDER, key=KEY)[1] == OK


def test_a_wrong_code_uses_an_attempt():
    code, state = issue_derived(order_id=ORDER, key=KEY)
    new_state, result = check_derived(state, wrong_code(code), order_id=ORDER, key=KEY)
    assert (result, new_state.failed_attempts, new_state.locked) == (WRONG, 1, False)


def test_five_wrong_attempts_lock_even_against_the_right_code():
    code, state = issue_derived(order_id=ORDER, key=KEY)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        state, result = check_derived(state, wrong_code(code), order_id=ORDER, key=KEY)
        assert result == WRONG and state.failed_attempts == attempt
    assert state.locked
    assert check_derived(state, code, order_id=ORDER, key=KEY)[1] == LOCKED


def test_four_wrong_attempts_do_not_lock():
    code, state = issue_derived(order_id=ORDER, key=KEY)
    for _ in range(MAX_ATTEMPTS - 1):
        state, _ = check_derived(state, wrong_code(code), order_id=ORDER, key=KEY)
    assert not state.locked
    assert check_derived(state, code, order_id=ORDER, key=KEY)[1] == OK


def test_input_that_is_not_six_digits_does_not_use_an_attempt():
    code, state = issue_derived(order_id=ORDER, key=KEY)
    for junk in ("", "12345", "1234567", "12345a", "abcdef", "12-345", "\uff11\uff12\uff13\uff14\uff15\uff16"):
        new_state, result = check_derived(state, junk, order_id=ORDER, key=KEY)
        assert result == MALFORMED and new_state == state


def test_a_code_belongs_to_one_order_and_one_key():
    # Uses the known vector: with six digits a random pair could rarely collide.
    assert derive_code(order_id=ORDER, nonce=NONCE, key=KEY) != derive_code(
        order_id=ORDER + 1, nonce=NONCE, key=KEY
    )
    assert derive_code(order_id=ORDER, nonce=NONCE, key=KEY) != derive_code(
        order_id=ORDER, nonce=NONCE, key=b"another key"
    )


def test_state_repr_hides_the_nonce():
    assert "abcdef" not in repr(DerivedCodeState(nonce="abcdef" * 5))


@given(guess=st.integers(min_value=0, max_value=999_999))
def test_only_the_real_code_ever_succeeds(guess):
    state = DerivedCodeState(nonce=NONCE)
    _, result = check_derived(state, f"{guess:06d}", order_id=ORDER, key=KEY)
    assert (result == OK) == (f"{guess:06d}" == "829022")
