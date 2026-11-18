"""M3 / known bug #1: handle_email_calendar reports real success, and its
signature and (bool, message) return shape are unchanged."""
import inspect
import sys
import types

import pytest


class Exec:
    def __init__(self, value):
        self.value = value

    def execute(self):
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


class FakeGmail:
    """users().messages().list/get/send/modify(...).execute()"""
    def __init__(self, listing=None, error=None):
        self.listing, self.error = listing or {"messages": []}, error

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **k):
        return Exec(self.error or self.listing)

    def get(self, **k):
        return Exec({"payload": {"headers": [{"name": "From", "value": "Ada <ada@example.com>"},
                                             {"name": "Subject", "value": "Hi"}]}})

    def send(self, **k):
        return Exec(self.error or {})


@pytest.fixture
def actions_real_agents(monkeypatch):
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "googleapiclient", types.ModuleType("googleapiclient"))
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery)
    for name in ("actions", "gmail_agent", "calendar_agent"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import actions
    import gmail_agent
    yield actions, gmail_agent
    for name in ("actions", "gmail_agent", "calendar_agent"):
        sys.modules.pop(name, None)


def test_signature_unchanged(actions_real_agents):
    actions, _ = actions_real_agents
    assert list(inspect.signature(actions.handle_email_calendar).parameters) == ["action_name", "param"]


def test_email_unread_failure_reports_false(actions_real_agents, monkeypatch):
    actions, gmail = actions_real_agents
    monkeypatch.setattr(gmail, "_service", lambda: FakeGmail(error=RuntimeError("HttpError 503")))
    result = actions.handle_email_calendar("email_unread", None)
    assert result == (False, "I couldn't fetch your emails right now.")   # was (True, ...)


def test_email_unread_success_reports_true(actions_real_agents, monkeypatch):
    actions, gmail = actions_real_agents
    monkeypatch.setattr(gmail, "_service", lambda: FakeGmail({"messages": [{"id": "1"}]}))
    assert actions.handle_email_calendar("email_unread", None) == (
        True, "You have 1 unread email. Ada: Hi")


def test_no_unread_is_success(actions_real_agents, monkeypatch):
    actions, gmail = actions_real_agents
    monkeypatch.setattr(gmail, "_service", lambda: FakeGmail())
    assert actions.handle_email_calendar("email_unread", None) == (True, "You have no unread emails.")


def test_email_send_failure_reports_false(actions_real_agents, monkeypatch):
    actions, gmail = actions_real_agents
    monkeypatch.setattr(gmail, "_service", lambda: FakeGmail(error=RuntimeError("quota")))
    assert actions.handle_email_calendar("email_send", "a@b.com|Hi|Body") == (
        False, "I wasn't able to send the email.")


def test_calendar_failure_reports_false(actions_real_agents, monkeypatch):
    actions, _ = actions_real_agents
    import calendar_agent
    def broken():
        raise RuntimeError("HttpError 503")
    monkeypatch.setattr(calendar_agent, "_service", broken)
    for action, param in [("calendar_today", None), ("calendar_upcoming", None),
                          ("calendar_range", "2026-11-20|2026-11-21"),
                          ("calendar_create", "Gym|2026-11-20|18:00|1"),
                          ("calendar_delete_date", "2026-11-20")]:
        ok, msg = actions.handle_email_calendar(action, param)
        assert ok is False and isinstance(msg, str) and msg, action


def test_unknown_action_shape_unchanged(actions_real_agents):
    actions, _ = actions_real_agents
    assert actions.handle_email_calendar("calendar_nonsense", None) == (False, None)
