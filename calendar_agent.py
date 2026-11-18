# calendar_agent.py
import re
import sys
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo
from googleapiclient.discovery import build
from google_auth import get_credentials, auth_failure


def _resolve_local_zone():
    """Returns (IANA name, tzinfo) for this PC. Falls back to UTC, loudly."""
    name, reason = None, "tzlocal returned no zone"
    try:
        from tzlocal import get_localzone_name
        name = get_localzone_name()
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"
    if name:
        try:
            return name, ZoneInfo(name)
        except Exception as e:
            reason = f"unknown timezone {name!r} ({type(e).__name__}: {e})"

    bar = "!" * 72
    print(f"{bar}\n[calendar] WARNING: could not detect your local timezone ({reason}).\n"
          f"[calendar] Falling back to UTC: 'today', delete-by-date and new event\n"
          f"[calendar] times will be off by your UTC offset.\n"
          f"[calendar] Fix: pip install -r requirements.txt  (needs tzlocal + tzdata)\n{bar}",
          file=sys.stderr)
    return "UTC", timezone.utc


LOCAL_TZ, LOCAL_ZONE = _resolve_local_zone()
print(f"[calendar] Using timezone: {LOCAL_TZ}")


_svc = None


def _service():
    """Calendar API client, built once and reused (it refreshes its own token)."""
    global _svc
    if _svc is None:
        _svc = build('calendar', 'v3', credentials=get_credentials())
    return _svc


def _fail(e, where, message):
    """Log a failure and return (False, spoken message). A dead Google sign-in
    gets the re-authorise message instead, and the cached client is dropped."""
    global _svc
    print(f"[calendar] {where} error: {e}")
    reauth = auth_failure(e)
    if reauth:
        _svc = None
        return False, reauth
    return False, message


def _now():
    return datetime.now(LOCAL_ZONE)


def _local_day_bounds(first_date, last_date=None):
    """[start, end) for whole local days: local midnight of first_date up to
    local midnight after last_date (defaults to first_date). Dates are YYYY-MM-DD."""
    first = date.fromisoformat(first_date.strip())
    last  = date.fromisoformat((last_date or first_date).strip())
    start = datetime(first.year, first.month, first.day, tzinfo=LOCAL_ZONE)
    end   = datetime(last.year, last.month, last.day, tzinfo=LOCAL_ZONE) + timedelta(days=1)
    return start, end


def _local_start(e):
    """Local start of an event: an aware datetime for timed events, a date for
    all-day events (which have start.date and no start.dateTime)."""
    start = e.get('start', {})
    if 'dateTime' in start:
        return datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00')).astimezone(LOCAL_ZONE)
    return date.fromisoformat(start.get('date', ''))


def _clock(e):
    """'6:00 PM' for a timed event, None for an all-day event."""
    start = _local_start(e)
    return start.strftime('%I:%M %p').lstrip('0') if isinstance(start, datetime) else None


def _event_when(e):
    """Spoken date (and time) of an event in local time, e.g. 'Friday November 20 at 6:00 PM'
    or 'Friday November 20, all day'."""
    start, clock = _local_start(e), _clock(e)
    day = f"{start:%A %B} {start.day}"
    return f"{day} at {clock}" if clock else f"{day}, all day"


def _local_start_date(e):
    start = _local_start(e)
    return start.date() if isinstance(start, datetime) else start


def _is_valid_date(s):
    return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', s.strip()))


def _is_valid_time(s):
    return bool(re.match(r'^\d{1,2}:\d{2}$', s.strip()))


def get_today_events():
    try:
        svc        = _service()
        start, end = _local_day_bounds(_now().date().isoformat())

        events = svc.events().list(
            calendarId='primary',
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])

        if not events:
            return True, "You have no events scheduled for today."

        parts = []
        for e in events:
            title = e.get('summary', 'Untitled')
            clock = _clock(e)
            parts.append(f"{title} at {clock}" if clock else f"{title}, all day")

        return True, f"Today you have {len(parts)} event{'s' if len(parts) > 1 else ''}: " + ", ".join(parts) + "."

    except Exception as e:
        return _fail(e, "Today", "I couldn't fetch your calendar right now.")


def get_upcoming_events(days=7):
    try:
        svc = _service()
        now = _now()
        end = now + timedelta(days=days)

        events = svc.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=10,
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])

        if not events:
            return True, f"You have no events in the next {days} days."

        parts = [f"{e.get('summary', 'Untitled')} on {_event_when(e)}" for e in events]
        return True, "Upcoming events: " + ". ".join(parts) + "."

    except Exception as e:
        return _fail(e, "Upcoming", "I couldn't fetch your upcoming events.")


def get_events_in_range(start_date_str, end_date_str):
    """Fetch events between two YYYY-MM-DD dates."""
    try:
        svc        = _service()
        start, end = _local_day_bounds(start_date_str, end_date_str)

        events = svc.events().list(
            calendarId='primary',
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            maxResults=20,
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])

        if not events:
            return True, f"You have no events between {start_date_str} and {end_date_str}."

        parts = [f"{e.get('summary', 'Untitled')} on {_event_when(e)}" for e in events]
        return True, "Events found: " + ". ".join(parts) + "."

    except Exception as e:
        return _fail(e, "Range", "I couldn't fetch events for that period.")


def create_event(title, date_str, time_str, duration_hours=1):
    if not _is_valid_date(date_str):
        print(f"[calendar] Bad date: '{date_str}'")
        return False, "I couldn't create the event. The date format was wrong. Please say a clear date like 'June 23rd'."

    if not _is_valid_time(time_str):
        print(f"[calendar] Bad time: '{time_str}'")
        return False, "I couldn't create the event. The time format was wrong. Please say a clear time like '3 PM'."

    try:
        svc   = _service()
        start = datetime.fromisoformat(f"{date_str.strip()}T{time_str.strip()}:00")
        end   = start + timedelta(hours=float(duration_hours))

        event = {
            'summary': title,
            'start':   {'dateTime': start.isoformat(), 'timeZone': LOCAL_TZ},
            'end':     {'dateTime': end.isoformat(),   'timeZone': LOCAL_TZ},
        }

        svc.events().insert(calendarId='primary', body=event).execute()
        spoken_time = start.strftime('%I:%M %p on %A %B %d').lstrip('0')
        return True, f"Done. I've added '{title}' to your calendar at {spoken_time}."

    except Exception as e:
        return _fail(e, "Create", "I wasn't able to create that event.")


MIN_QUERY_CHARS  = 3     # "a", "it", "x" etc. are too vague to delete by
FUZZY_MIN_RATIO  = 0.8   # spelling slips like "drink waters" -> "Drink water"


def _words(text):
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def _match_score(query_words, title):
    """0 means no match. Exact title (3) > every query word present as a whole
    word in the title (2-3, more of the title covered scores higher) > close
    spelling of the whole title (0.8-1). Substrings inside words never match."""
    title_words = _words(title)
    if not title_words:
        return 0.0
    if title_words == query_words:
        return 3.0
    if all(w in title_words for w in query_words):
        return 2.0 + min(1.0, len(query_words) / len(title_words)) * 0.99
    ratio = SequenceMatcher(None, " ".join(query_words), " ".join(title_words)).ratio()
    return ratio if ratio >= FUZZY_MIN_RATIO else 0.0


def find_event_by_name(event_title):
    """Best match for event_title among the next 20 events.
    Returns ({'id', 'title', 'when'}, None) or (None, spoken reason)."""
    query_words = _words(event_title)
    if len("".join(query_words)) < MIN_QUERY_CHARS:
        return None, "Please tell me the name of the event you want to delete."

    try:
        events = _service().events().list(
            calendarId='primary',
            timeMin=datetime.now(timezone.utc).isoformat(),
            maxResults=20,
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])
    except Exception as e:
        return None, _fail(e, "Find", "I couldn't check your calendar right now.")[1]

    best, best_score = None, 0.0
    for e in events:                      # sorted by start: ties keep the earliest
        score = _match_score(query_words, e.get('summary', ''))
        if score > best_score:
            best, best_score = e, score

    if not best:
        return None, f"I couldn't find an event called '{event_title}' on your calendar."
    print(f"[calendar] '{event_title}' matched '{best.get('summary')}' (score {best_score:.2f})")
    return {"id": best['id'], "title": best.get('summary', 'Untitled'),
            "when": _event_when(best)}, None


def delete_event_by_id(event_id, title):
    """Delete one specific event. Returns (success, spoken message)."""
    try:
        _service().events().delete(calendarId='primary', eventId=event_id).execute()
        return True, f"Done. I've removed '{title}' from your calendar."
    except Exception as e:
        return _fail(e, "Delete", "I wasn't able to delete that event.")


def delete_event(event_title):
    """Delete the best match for the given title (today onwards). Kept for
    callers that don't confirm first; main.py uses find + delete_event_by_id.
    Returns (success, spoken message)."""
    match, reason = find_event_by_name(event_title)
    if not match:
        return False, reason
    return delete_event_by_id(match["id"], match["title"])


def delete_events_by_date(date_str):
    """Delete every event that STARTS on a specific local date (YYYY-MM-DD).
    Events that merely overlap it (a trip from the day before, a party running
    past midnight) are left alone. Returns (success, spoken message)."""
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str.strip()):
        return False, "Invalid date format for deletion."

    try:
        svc        = _service()
        start, end = _local_day_bounds(date_str)

        events = svc.events().list(
            calendarId='primary',
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])
        target = start.date()
        events = [e for e in events if _local_start_date(e) == target]

        try:
            readable = datetime.fromisoformat(date_str).strftime('%A %B %d')
        except Exception:
            readable = date_str

        if not events:
            return True, f"No events found on {readable}."

        deleted, failed = [], []
        for e in events:
            title = e.get('summary', 'Untitled')
            try:
                svc.events().delete(calendarId='primary', eventId=e['id']).execute()
                deleted.append(title)
            except Exception as err:
                print(f"[calendar] Could not delete '{title}': {err}")
                failed.append(title)

        def _plural(n):
            return f"{n} event{'s' if n != 1 else ''}"

        done_msg = f"Deleted {_plural(len(deleted))} on {readable}: {', '.join(deleted)}."
        if not failed:
            return True, f"Done. {done_msg}"
        if not deleted:
            return False, f"I wasn't able to delete any events on {readable}. Failed: {', '.join(failed)}."
        return False, f"{done_msg} I couldn't delete {_plural(len(failed))}: {', '.join(failed)}."

    except Exception as e:
        return _fail(e, "Delete date", "I wasn't able to delete those events.")
