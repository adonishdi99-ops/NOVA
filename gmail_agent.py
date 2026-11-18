# gmail_agent.py
import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google_auth import get_credentials, auth_failure


_svc = None


def _service():
    """Gmail API client, built once and reused (it refreshes its own token)."""
    global _svc
    if _svc is None:
        _svc = build('gmail', 'v1', credentials=get_credentials())
    return _svc


def _fail(e, where, message):
    """Log a failure and return (False, spoken message). A dead Google sign-in
    gets the re-authorise message instead, and the cached client is dropped."""
    global _svc
    print(f"[gmail] {where} error: {e}")
    reauth = auth_failure(e)
    if reauth:
        _svc = None
        return False, reauth
    return False, message


def _decode_body(payload):
    """Extract plain text body from a Gmail message payload."""
    if 'data' in payload.get('body', {}):
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    for part in payload.get('parts', []):
        if part.get('mimeType') == 'text/plain':
            data = part['body'].get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    return ""


def get_unread_emails(max_results=5):
    """Returns (success, spoken summary of unread emails)."""
    try:
        svc     = _service()
        results = svc.users().messages().list(
            userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        if not messages:
            return True, "You have no unread emails."

        summaries = []
        for msg in messages:
            detail  = svc.users().messages().get(userId='me', id=msg['id'], format='metadata',
                        metadataHeaders=['From', 'Subject']).execute()
            headers = {h['name']: h['value'] for h in detail['payload']['headers']}
            sender  = headers.get('From', 'Unknown').split('<')[0].strip()
            subject = headers.get('Subject', 'No subject')
            summaries.append(f"{sender}: {subject}")

        count = len(summaries)
        intro = f"You have {count} unread email{'s' if count > 1 else ''}. "
        return True, intro + ". ".join(summaries)

    except Exception as e:
        return _fail(e, "Unread", "I couldn't fetch your emails right now.")


def read_latest_email():
    """Returns (success, spoken content of the most recent unread email)."""
    try:
        svc     = _service()
        results = svc.users().messages().list(
            userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=1
        ).execute()

        messages = results.get('messages', [])
        if not messages:
            return True, "You have no unread emails."

        msg_id  = messages[0]['id']
        detail  = svc.users().messages().get(userId='me', id=msg_id, format='full').execute()
        headers = {h['name']: h['value'] for h in detail['payload']['headers']}
        sender  = headers.get('From', 'Unknown').split('<')[0].strip()
        subject = headers.get('Subject', 'No subject')
        body    = _decode_body(detail['payload'])[:500]  # cap at 500 chars for voice

        # Mark as read
        svc.users().messages().modify(
            userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}
        ).execute()

        return True, f"Email from {sender}. Subject: {subject}. {body}"

    except Exception as e:
        return _fail(e, "Read", "I couldn't read that email right now.")


def send_email(to, subject, body):
    """Send an email. Returns (success, spoken message)."""
    try:
        svc     = _service()
        message = MIMEText(body)
        message['to']      = to
        message['subject'] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        svc.users().messages().send(userId='me', body={'raw': raw}).execute()
        return True, f"Email sent to {to}."
    except Exception as e:
        return _fail(e, "Send", "I wasn't able to send the email.")
