"""In-memory stand-in for the Google Calendar `events()` API.

list() returns events overlapping [timeMin, timeMax), sorted by start, the way
Google does with singleEvents=True / orderBy=startTime. All-day events carry
start.date / end.date (end exclusive) and are placed on the calendar's own
timezone, like Google does.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

CALENDAR_ZONE = ZoneInfo("Africa/Lagos")


def _ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _bound(part):
    if "dateTime" in part:
        return _ts(part["dateTime"])
    d = date.fromisoformat(part["date"])
    return datetime(d.year, d.month, d.day, tzinfo=CALENDAR_ZONE)


class _Call:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class FakeEvents:
    def __init__(self, items, fail_ids=()):
        self.items = list(items)
        self.fail_ids = set(fail_ids)
        self.list_calls = []
        self.deleted = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        t_min = _ts(kwargs["timeMin"])
        t_max = _ts(kwargs["timeMax"]) if "timeMax" in kwargs else None
        hits = [e for e in self.items
                if _bound(e["end"]) > t_min
                and (t_max is None or _bound(e["start"]) < t_max)]
        hits.sort(key=lambda e: _bound(e["start"]))
        return _Call(lambda: {"items": hits[:kwargs.get("maxResults", 250)]})

    def delete(self, calendarId, eventId):
        def run():
            if eventId in self.fail_ids:
                raise RuntimeError(f"HttpError 500 deleting {eventId}")
            self.deleted.append(eventId)
            self.items = [e for e in self.items if e["id"] != eventId]
            return ""
        return _Call(run)


class FakeService:
    def __init__(self, items, fail_ids=()):
        self._events = FakeEvents(items, fail_ids)

    def events(self):
        return self._events


def event(event_id, title, start, end):
    return {"id": event_id, "summary": title,
            "start": {"dateTime": start}, "end": {"dateTime": end}}


def all_day_event(event_id, title, start_date, end_date):
    """end_date is exclusive, as in the Google API (a one-day event on the 20th
    has end 2026-11-21)."""
    return {"id": event_id, "summary": title,
            "start": {"date": start_date}, "end": {"date": end_date}}
