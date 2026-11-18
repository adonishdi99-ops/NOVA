"""M9 / H2 / H1 behaviour in main._handle_command and main._process_command."""


def _think_returns(main_mod, spoken, action, param):
    main_mod.think = lambda command: (spoken, action, param)


def test_system_sleep_requires_confirmation(main_mod):
    _think_returns(main_mod, "", "system_sleep", None)
    main_mod._test_calls["listen"].append("no")
    main_mod._handle_command("go to sleep")
    assert main_mod._test_calls["executed"] == []
    assert "Are you sure you want to put your PC to sleep?" in main_mod._test_calls["spoken"]


def test_system_sleep_runs_after_yes(main_mod):
    _think_returns(main_mod, "", "system_sleep", None)
    main_mod._test_calls["listen"].append("yes")
    main_mod._handle_command("go to sleep")
    assert main_mod._test_calls["executed"] == [("system_sleep", None)]


def test_email_send_reads_back_recipient_and_subject(main_mod):
    _think_returns(main_mod, "", "email_send", "john@example.com|Lunch|See you at 1")
    main_mod._test_calls["listen"].append("no")
    main_mod._handle_command("email john about lunch")
    assert "Send an email to john@example.com with the subject 'Lunch'?" in main_mod._test_calls["spoken"]
    assert main_mod._test_calls["email_calendar"] == []


def test_email_send_sends_after_yes(main_mod):
    _think_returns(main_mod, "", "email_send", "john@example.com|Lunch|See you at 1")
    main_mod._test_calls["listen"].append("yes send it")
    main_mod._handle_command("email john about lunch")
    assert main_mod._test_calls["email_calendar"] == [
        ("email_send", "john@example.com|Lunch|See you at 1")]


def test_failing_command_is_logged_spoken_and_loop_continues(main_mod, capsys):
    def boom(command):
        raise OSError("broken shortcut")
    main_mod.think = boom
    assert main_mod._process_command("open thing") is False
    assert main_mod._test_calls["spoken"][-1] == "Sorry, something went wrong with that."
    assert "OSError: broken shortcut" in capsys.readouterr().err


def test_process_command_still_returns_stop_for_exit(main_mod):
    assert main_mod._process_command("goodbye nova") is True
