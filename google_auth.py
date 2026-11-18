# google_auth.py
import os
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Always look for files in the same folder as this script
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')
TOKEN_FILE       = os.path.join(BASE_DIR, 'token.json')

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar',
]

REAUTH_MESSAGE = ("My Google sign-in has expired or was revoked. Delete token.json "
                  "in the NOVA folder and restart me to sign in again.")


class ReauthRequired(Exception):
    """The saved Google token can no longer be refreshed; the user must sign in again."""


# Cached for the whole session so token.json isn't re-read on every request.
_creds = None


def get_credentials():
    global _creds
    if _creds and _creds.valid:
        return _creds

    creds = _creds
    if creds is None and os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                _creds = None
                print(f"[google_auth] Token refresh failed: {e}")
                raise ReauthRequired(REAUTH_MESSAGE) from e
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())

    _creds = creds
    return creds


def auth_failure(error):
    """If `error` means the Google sign-in is dead, forget the cached credentials
    and return the spoken fix; otherwise None. Covers refresh failures raised by
    get_credentials() and by API calls that refresh the token mid-request."""
    global _creds
    if isinstance(error, (ReauthRequired, RefreshError)):
        _creds = None
        return REAUTH_MESSAGE
    return None
