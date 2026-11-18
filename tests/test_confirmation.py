import pytest


@pytest.mark.parametrize("reply", [
    "yes", "yeah do it", "go ahead", "sure", "okay", "yes please",
    "that's correct", "Yes, proceed.",
])
def test_affirmative_replies_confirm(main_mod, reply):
    assert main_mod.is_confirmed(reply) is True


@pytest.mark.parametrize("reply", [
    # Negations that the old substring match accepted as "yes"
    "no don't do it", "i'm not sure", "no that's not right", "uh okay no",
    "yes wait", "yes, cancel that", "sure, actually stop", "dont do it",
    "don\u2019t do it",           # curly apostrophe from typed input
    "do not proceed",
    # Substrings of confirm words are not whole words
    "yesterday", "surely", "righteous", "okayish",
    # Unclear or empty: default is cancel
    "", "   ", "hmm", "maybe later", None,
])
def test_negative_or_unclear_replies_cancel(main_mod, reply):
    assert main_mod.is_confirmed(reply) is False


def test_ask_confirm_speaks_cancelled_on_negative(main_mod):
    main_mod._test_calls["listen"].append("no don't do it")
    assert main_mod.ask_confirm("Are you sure?") is False
    assert main_mod._test_calls["spoken"] == ["Are you sure?", "Cancelled."]


def test_ask_confirm_silence_cancels(main_mod):
    # voice.listen() returns "" on timeout (see test_voice_timeout.py)
    assert main_mod.ask_confirm("Are you sure?") is False
