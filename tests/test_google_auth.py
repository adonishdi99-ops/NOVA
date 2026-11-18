"""M12: cached credentials/services and RefreshError handling."""
import sys
import types

import pytest
from google.auth.exceptions import RefreshError


class FakeCreds:
    def __init__(self, valid=True, expired=False, refresh_token="r", refresh_error=None):
        self.valid, self.expired, self.refresh_token = valid, expired, refresh_token
        self.refresh_error, self.refreshed = refresh_error, 0

    def refresh(self, request):
        self.refreshed += 1
        if self.refresh_error:
            raise self.refresh_error
        self.valid, self.expired = True, False

    def to_json(self):
        return '{"token": "fake"}'


@pytest.fixture
def auth(monkeypatch, tmp_path):
    monkeypatch.delitem(sys.modules, "google_auth", raising=False)
    import google_auth
    token = tmp_path / "token.json"
    token.write_text("{}")
    monkeypatch.setattr(google_auth, "TOKEN_FILE", str(token))
    google_auth._token_path = token
    yield google_auth
    sys.modules.pop("google_auth", None)


def load_returns(auth, monkeypatch, creds):
    loads = []
    monkeypatch.setattr(auth.Credentials, "from_authorized_user_file",
                        lambda path, scopes: loads.append(path) or creds)
    return loads


def test_valid_credentials_are_cached(auth, monkeypatch):
    creds = FakeCreds()
    loads = load_returns(auth, monkeypatch, creds)
    assert auth.get_credentials() is creds
    assert auth.get_credentials() is creds
    assert len(loads) == 1                       # token.json read once, not per call


def test_expired_token_is_refreshed_and_saved(auth, monkeypatch):
    creds = FakeCreds(valid=False, expired=True)
    load_returns(auth, monkeypatch, creds)
    assert auth.get_credentials() is creds and creds.refreshed == 1
    assert auth._token_path.read_text() == '{"token": "fake"}'


def test_refresh_error_asks_user_to_reauthorise(auth, monkeypatch):
    creds = FakeCreds(valid=False, expired=True,
                      refresh_error=RefreshError("invalid_grant: Token has been expired or revoked."))
    load_returns(auth, monkeypatch, creds)
    with pytest.raises(auth.ReauthRequired) as exc:
        auth.get_credentials()
    assert "Delete token.json" in str(exc.value)
    assert auth._creds is None


@pytest.mark.parametrize("error, expected", [
    (RefreshError("invalid_grant"), True),
    (None, True),        # ReauthRequired, built below
    (RuntimeError("HttpError 503"), False),
])
def test_auth_failure_recognises_dead_sign_in(auth, error, expected):
    error = error or auth.ReauthRequired(auth.REAUTH_MESSAGE)
    auth._creds = FakeCreds()
    result = auth.auth_failure(error)
    assert (result == auth.REAUTH_MESSAGE) is expected
    assert (auth._creds is None) is expected


@pytest.fixture
def gmail(monkeypatch, auth):
    built = []
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = lambda *a, **k: built.append(a) or object()
    monkeypatch.setitem(sys.modules, "googleapiclient", types.ModuleType("googleapiclient"))
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery)
    monkeypatch.delitem(sys.modules, "gmail_agent", raising=False)
    import gmail_agent
    monkeypatch.setattr(gmail_agent, "get_credentials", lambda: FakeCreds())
    gmail_agent._built = built
    yield gmail_agent
    sys.modules.pop("gmail_agent", None)


def test_gmail_service_is_built_once(gmail):
    first = gmail._service()
    assert gmail._service() is first and len(gmail._built) == 1


def test_gmail_refresh_error_mid_request_gives_reauth_message_and_resets(gmail, auth):
    class Svc:
        def users(self):
            raise RefreshError("invalid_grant")
    gmail._svc = Svc()
    assert gmail.get_unread_emails() == (False, auth.REAUTH_MESSAGE)
    assert gmail._svc is None                    # rebuilt on the next request
