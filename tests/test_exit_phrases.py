import pytest


@pytest.mark.parametrize("command", [
    "goodbye nova", "bye nova", "Nova, shut down.", "shut down nova",
    "okay bye bye nova", "stop nova", "exit nova please", "turn off nova",
])
def test_exit_phrases_stop_nova(main_mod, command):
    assert main_mod.wants_shutdown(command) is True


@pytest.mark.parametrize("command", [
    "don't stop nova",              # negated
    "do not turn off nova",
    "nova never shut down",
    "nova, tell my mum bye",        # old loose bye+nova rule
    "play bye bye by casanova",     # "nova" inside another word
    "shut down my pc",              # PC shutdown is a separate, gated action
    "open spotify",
    "",
])
def test_non_exit_commands_keep_running(main_mod, command):
    assert main_mod.wants_shutdown(command) is False
