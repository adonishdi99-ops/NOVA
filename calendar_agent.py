# calendar_agent.py
import re
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from google_auth import get_credentials

try:
    from tzlocal import get_localzone_name
    LOCAL_TZ = get_localzone_name()
except Exception:
    LOCAL_TZ = "UTC"

print(f"[calendar] Using timezone: {LOCAL_TZ}")


def _service():
    return build('calendar', 'v3', credentials=get_credentials())


def _fmt_time(dt_str):
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00')).astimezone()
        return dt.strftime('%I:%M %p').lstrip('0')
    except Exception:
        return dt_str


def _is_valid_date(s):
    return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', s.strip()))


def _is_valid_time(s):
    return bool(re.match(r'^\d{1,2}:\d{2}$', s.strip()))


def get_today_events():
    try:
        svc   = _service()
        now   = datetime.now(timezone.utc)
        start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        end   = start + timedelta(days=1)

        events = svc.events().list(
            calendarId='primary',
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])

        if not events:
            return "You have no events scheduled for today."

        parts = []
        for e in events:
            title    = e.get('summary', 'Untitled')
            start_dt = e['start'].get('dateTime', e['start'].get('date', ''))
            parts.append(f"{title} at {_fmt_time(start_dt)}")

        return f"Today you have {len(parts)} event{'s' if len(parts) > 1 else ''}: " + ", ".join(parts) + "."

    except Exception as e:
        print(f"[calendar] Error: {e}")
        return "I couldn't fetch your calendar right now."


def get_upcoming_events(days=7):
    try:
        svc = _service()
        now = datetime.now(timezone.utc)
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
            return f"You have no events in the next {days} days."

        parts = []
        for e in events:
            title    = e.get('summary', 'Untitled')
            start_dt = e['start'].get('dateTime', e['start'].get('date', ''))
            try:
                dt    = datetime.fromisoformat(start_dt.replace('Z', '+00:00')).astimezone()
                label = dt.strftime('%A %B %d at %I:%M %p').lstrip('0')
            except Exception:
                label = start_dt
            parts.append(f"{title} on {label}")

        return "Upcoming events: " + ". ".join(parts) + "."

    except Exception as e:
        print(f"[calendar] Error: {e}")
        return "I couldn't fetch your upcoming events."


def get_events_in_range(start_date_str, end_date_str):
    """Fetch events between two YYYY-MM-DD dates."""
    try:
        svc   = _service()
        start = datetime.fromisoformat(f"{start_date_str}T00:00:00").replace(tzinfo=timezone.utc)
        end   = datetime.fromisoformat(f"{end_date_str}T23:59:59").replace(tzinfo=timezone.utc)

        events = svc.events().list(
            calendarId='primary',
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            maxResults=20,
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])

        if not events:
            return f"You have no events between {start_date_str} and {end_date_str}."

        parts = []
        for e in events:
            title    = e.get('summary', 'Untitled')
            start_dt = e['start'].get('dateTime', e['start'].get('date', ''))
            try:
                dt    = datetime.fromisoformat(start_dt.replace('Z', '+00:00')).astimezone()
                label = dt.strftime('%A %B %d at %I:%M %p').lstrip('0')
            except Exception:
                label = start_dt
            parts.append(f"{title} on {label}")

        return "Events found: " + ". ".join(parts) + "."

    except Exception as e:
        print(f"[calendar] Range error: {e}")
        return "I couldn't fetch events for that period."


def create_event(title, date_str, time_str, duration_hours=1):
    if not _is_valid_date(date_str):
        print(f"[calendar] Bad date: '{date_str}'")
        return "I couldn't create the event. The date format was wrong. Please say a clear date like 'June 23rd'."

    if not _is_valid_time(time_str):
        print(f"[calendar] Bad time: '{time_str}'")
        return "I couldn't create the event. The time format was wrong. Please say a clear time like '3 PM'."

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
        return f"Done. I've added '{title}' to your calendar at {spoken_time}."

    except Exception as e:
        print(f"[calendar] Create error: {e}")
        return "I wasn't able to create that event."


def delete_event(event_title):
    """Delete the first event matching the given title (today onwards)."""
    try:
        svc = _service()
        now = datetime.now(timezone.utc)

        events = svc.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            maxResults=20,
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])

        for e in events:
            if event_title.lower() in e.get('summary', '').lower():
                svc.events().delete(calendarId='primary', eventId=e['id']).execute()
                return f"Done. I've removed '{e.get('summary')}' from your calendar."

        return f"I couldn't find an event called '{event_title}' on your calendar."

    except Exception as e:
        print(f"[calendar] Delete error: {e}")
        return "I wasn't able to delete that event."


def delete_events_by_date(date_str):
    """Delete ALL events on a specific date (YYYY-MM-DD)."""
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str.strip()):
        return "Invalid date format for deletion."

    try:
        svc   = _service()
        start = datetime.fromisoformat(f"{date_str}T00:00:00").replace(tzinfo=timezone.utc)
        end   = datetime.fromisoformat(f"{date_str}T23:59:59").replace(tzinfo=timezone.utc)

        events = svc.events().list(
            calendarId='primary',
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])

        try:
            readable = datetime.fromisoformat(date_str).strftime('%A %B %d')
        except Exception:
            readable = date_str

        if not events:
            return f"No events found on {readable}."

        deleted = []
        for e in events:
            title = e.get('summary', 'Untitled')
            svc.events().delete(calendarId='primary', eventId=e['id']).execute()
            deleted.append(title)

        names = ", ".join(deleted)
        return f"Done. Deleted {len(deleted)} event{'s' if len(deleted) > 1 else ''} on {readable}: {names}."

    except Exception as e:
        print(f"[calendar] Delete date error: {e}")
        return "I wasn't able to delete those events."