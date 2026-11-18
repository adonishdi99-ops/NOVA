"""H3/H4/M6/M7: calendar day boundaries in local time, loud UTC fallback,
delete-by-name matching, and honest delete-by-date reporting.

Test zone: Africa/Lagos (WAT, UTC+1, no DST).
"""
import sys
import types
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from fake_calendar import FakeService, event

LAGOS = ZoneInfo("Africa/Lagos")


@pytest.fixture
def cal(monkeypatch):
    # calendar_agent imports the Google client + OAuth helper at module level.
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "googleapiclient", types.ModuleType("googleapiclient"))
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery)
    monkeypatch.setitem(sys.modules, "google_auth",
                        types.SimpleNamespace(get_credentials=lambda: None))
    monkeypatch.delitem(sys.modules, "calendar_agent", raising=False)
    import calendar_agent
    monkeypatch.setattr(calendar_agent, "LOCAL_TZ", "Africa/Lagos")
    monkeypatch.setattr(calendar_agent, "LOCAL_ZONE", LAGOS)
    yield calendar_agent
    sys.modules.pop("calendar_agent", None)


def use_service(cal, monkeypatch, items, fail_ids=()):
    svc = FakeService(items, fail_ids)
    monkeypatch.setattr(cal, "_service", lambda: svc)
    return svc.events()


# Events around the 20th, in Lagos local time (+01:00)
EARLY_20TH = event("early20", "Early run", "2026-11-20T00:30:00+01:00", "2026-11-20T01:00:00+01:00")
NOON_20TH  = event("noon20", "Lunch", "2026-11-20T12:00:00+01:00", "2026-11-20T13:00:00+01:00")
LATE_19TH  = event("late19", "Late film", "2026-11-19T23:30:00+01:00", "2026-11-19T23:59:00+01:00")
EARLY_21ST = event("early21", "Night bus", "2026-11-21T00:30:00+01:00", "2026-11-21T01:00:00+01:00")
ALL = [LATE_19TH, EARLY_20TH, NOON_20TH, EARLY_21ST]


# ── H3: local day boundaries ────────────────────────────────────────────────
def test_day_bounds_are_local_midnight_to_midnight(cal):
    start, end = cal._local_day_bounds("2026-11-20")
    assert start.isoformat() == "2026-11-20T00:00:00+01:00"
    assert end.isoformat() == "2026-11-21T00:00:00+01:00"


def test_range_bounds_include_whole_last_day(cal):
    start, end = cal._local_day_bounds("2026-11-20", "2026-11-22")
    assert (start.isoformat(), end.isoformat()) == (
        "2026-11-20T00:00:00+01:00", "2026-11-23T00:00:00+01:00")


def test_delete_by_date_hits_exactly_the_local_day(cal, monkeypatch):
    events = use_service(cal, monkeypatch, ALL)
    msg = cal.delete_events_by_date("2026-11-20")
    # 00:30 on the 20th is included (UTC bounds missed it); 00:30 on the
    # 21st is NOT deleted (UTC bounds deleted it); 23:30 on the 19th is safe.
    assert sorted(events.deleted) == ["early20", "noon20"]
    assert msg == "Done. Deleted 2 events on Friday November 20: Early run, Lunch."


def test_today_at_0030_local_is_the_local_date(cal, monkeypatch):
    # 00:30 in Lagos on the 20th is still 23:30 on the 19th in UTC.
    monkeypatch.setattr(cal, "_now", lambda: datetime(2026, 11, 20, 0, 30, tzinfo=LAGOS))
    events = use_service(cal, monkeypatch, ALL)
    msg = cal.get_today_events()
    call = events.list_calls[0]
    assert (call["timeMin"], call["timeMax"]) == (
        "2026-11-20T00:00:00+01:00", "2026-11-21T00:00:00+01:00")
    assert msg.startswith("Today you have 2 events: Early run at ")
    assert "Late film" not in msg and "Night bus" not in msg


def test_range_query_uses_local_days(cal, monkeypatch):
    events = use_service(cal, monkeypatch, ALL)
    msg = cal.get_events_in_range("2026-11-20", "2026-11-20")
    assert "Early run" in msg and "Lunch" in msg and "Night bus" not in msg
    assert events.list_calls[0]["timeMax"] == "2026-11-21T00:00:00+01:00"


# ── H4: loud fallback to UTC ────────────────────────────────────────────────
def test_tz_fallback_is_loud(cal, monkeypatch, capsys):
    broken = types.ModuleType("tzlocal")
    def boom():
        raise RuntimeError("no zone")
    broken.get_localzone_name = boom
    monkeypatch.setitem(sys.modules, "tzlocal", broken)
    name, zone = cal._resolve_local_zone()
    assert name == "UTC" and zone.utcoffset(None).total_seconds() == 0
    err = capsys.readouterr().err
    assert "WARNING: could not detect your local timezone" in err and "RuntimeError: no zone" in err


def test_tz_unknown_zone_name_is_loud(cal, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "tzlocal",
                        types.SimpleNamespace(get_localzone_name=lambda: "Mars/Olympus_Mons"))
    assert cal._resolve_local_zone()[0] == "UTC"
    assert "unknown timezone 'Mars/Olympus_Mons'" in capsys.readouterr().err


def test_tz_detected_zone_is_used(cal, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "tzlocal",
                        types.SimpleNamespace(get_localzone_name=lambda: "Africa/Lagos"))
    name, zone = cal._resolve_local_zone()
    assert name == "Africa/Lagos" and str(zone) == "Africa/Lagos"
    assert "WARNING" not in capsys.readouterr().err


# ── M7: delete-by-date reports deleted and failed ───────────────────────────
def test_delete_by_date_partial_failure_reports_both(cal, monkeypatch):
    events = use_service(cal, monkeypatch, ALL, fail_ids={"noon20"})
    msg = cal.delete_events_by_date("2026-11-20")
    assert events.deleted == ["early20"]
    assert msg == ("Deleted 1 event on Friday November 20: Early run. "
                   "I couldn't delete 1 event: Lunch.")


def test_delete_by_date_total_failure(cal, monkeypatch):
    use_service(cal, monkeypatch, ALL, fail_ids={"early20", "noon20"})
    msg = cal.delete_events_by_date("2026-11-20")
    assert msg == "I wasn't able to delete any events on Friday November 20. Failed: Early run, Lunch."


# ── M6: delete-by-name matching ─────────────────────────────────────────────
UPCOMING = [
    event("gym1", "Gym with Sarah", "2099-11-24T18:00:00+01:00", "2099-11-24T19:00:00+01:00"),
    event("gymn", "Gymnastics class", "2099-11-23T10:00:00+01:00", "2099-11-23T11:00:00+01:00"),
    event("water1", "Drink water", "2099-11-22T09:00:00+01:00", "2099-11-22T09:05:00+01:00"),
    event("water2", "Drink water", "2099-11-23T09:00:00+01:00", "2099-11-23T09:05:00+01:00"),
    event("team", "Team meeting", "2099-11-25T14:00:00+01:00", "2099-11-25T15:00:00+01:00"),
    event("meet", "Meeting", "2099-11-26T14:00:00+01:00", "2099-11-26T15:00:00+01:00"),
]


@pytest.mark.parametrize("query, expected_id", [
    ("gym", "gym1"),                  # whole word, not "Gymnastics"
    ("gym with sarah", "gym1"),
    ("Drink water", "water1"),        # earliest of identical titles
    ("drink waters", "water1"),       # close spelling
    ("meeting", "meet"),              # exact title beats partial "Team meeting"
    ("team meeting", "team"),
])
def test_find_event_picks_best_match(cal, monkeypatch, query, expected_id):
    use_service(cal, monkeypatch, UPCOMING)
    match, reason = cal.find_event_by_name(query)
    assert reason is None and match["id"] == expected_id


def test_find_event_returns_real_title_and_local_date(cal, monkeypatch):
    use_service(cal, monkeypatch, UPCOMING)
    match, _ = cal.find_event_by_name("gym")
    assert match == {"id": "gym1", "title": "Gym with Sarah",
                     "when": "Tuesday November 24 at 6:00 PM"}


@pytest.mark.parametrize("query", ["gymn", "sarah gym party", "dentist", "wat"])
def test_find_event_rejects_weak_matches(cal, monkeypatch, query):
    use_service(cal, monkeypatch, UPCOMING)
    match, reason = cal.find_event_by_name(query)
    assert match is None and "couldn't find" in reason


@pytest.mark.parametrize("query", ["", "a", "it", "  x  "])
def test_find_event_rejects_too_short_queries(cal, monkeypatch, query):
    events = use_service(cal, monkeypatch, UPCOMING)
    match, reason = cal.find_event_by_name(query)
    assert match is None and "name of the event" in reason
    assert events.list_calls == []    # didn't even query the calendar


def test_delete_event_by_id_deletes_only_that_event(cal, monkeypatch):
    events = use_service(cal, monkeypatch, UPCOMING)
    ok, msg = cal.delete_event_by_id("water2", "Drink water")
    assert ok and events.deleted == ["water2"]
    assert msg == "Done. I've removed 'Drink water' from your calendar."


def test_delete_event_by_id_failure(cal, monkeypatch):
    use_service(cal, monkeypatch, UPCOMING, fail_ids={"gym1"})
    assert cal.delete_event_by_id("gym1", "Gym with Sarah") == (
        False, "I wasn't able to delete that event.")
