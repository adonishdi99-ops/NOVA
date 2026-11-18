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


# ── M6: delete-by-name confirms the real event, then deletes it by id ───────
GYM = {"id": "gym1", "title": "Gym with Sarah", "when": "Tuesday November 24 at 6:00 PM"}


def test_calendar_delete_confirms_real_title_and_date(main_mod):
    _think_returns(main_mod, "", "calendar_delete", "gym")
    main_mod.find_event_by_name = lambda name: (GYM, None)
    main_mod._test_calls["listen"].append("yes")
    main_mod._handle_command("delete gym")
    assert ("Are you sure you want to delete 'Gym with Sarah' on Tuesday November 24 "
            "at 6:00 PM?") in main_mod._test_calls["spoken"]
    assert main_mod._test_calls["deleted_ids"] == ["gym1"]
    assert main_mod._test_calls["spoken"][-1] == "Removed Gym with Sarah"


def test_calendar_delete_cancel_deletes_nothing(main_mod):
    _think_returns(main_mod, "", "calendar_delete", "gym")
    main_mod.find_event_by_name = lambda name: (GYM, None)
    main_mod._test_calls["listen"].append("no")
    main_mod._handle_command("delete gym")
    assert main_mod._test_calls["deleted_ids"] == []


def test_calendar_delete_no_match_speaks_reason_without_asking(main_mod):
    _think_returns(main_mod, "", "calendar_delete", "dentist")
    main_mod.find_event_by_name = lambda name: (None, "I couldn't find an event called 'dentist'.")
    main_mod._handle_command("delete dentist")
    assert main_mod._test_calls["spoken"] == ["I couldn't find an event called 'dentist'."]
    assert main_mod._test_calls["deleted_ids"] == []


def test_calendar_delete_all_day_confirmation_text(main_mod):
    _think_returns(main_mod, "", "calendar_delete", "birthday")
    main_mod.find_event_by_name = lambda name: (
        {"id": "bday", "title": "Mum's birthday", "when": "Friday November 20, all day"}, None)
    main_mod._handle_command("delete mum's birthday")
    assert ("Are you sure you want to delete 'Mum's birthday' on Friday November 20, all day?"
            in main_mod._test_calls["spoken"])


def test_blocked_app_gets_spoken_reason(main_mod):
    _think_returns(main_mod, "", "open_app", "diskpart")
    main_mod.execute = lambda a, p=None: False
    main_mod.is_blocked_app = lambda name: name == "diskpart"
    main_mod._handle_command("open diskpart")
    assert main_mod._test_calls["spoken"][-1] == (
        "I won't open diskpart. It's a system tool I'm not allowed to launch.")


def test_ui_url_is_absolute_and_independent_of_cwd(main_mod, tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.chdir(tmp_path)                  # start NOVA from some other folder
    url = main_mod._ui_url()
    assert url.startswith("file:///") and url.endswith("/UI.html")
    expected = Path(main_mod.__file__).resolve().parent / "UI.html"
    assert expected.exists() and url == expected.as_uri()
