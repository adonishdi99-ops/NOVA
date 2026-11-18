import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _module(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


@pytest.fixture
def main_mod(monkeypatch):
    """Import main.py with its heavy/OS-specific dependencies stubbed out.

    server/voice/brain/actions/calendar_agent need a WebSocket loop, mic + speakers, a Groq
    key and Windows. Tests drive main's logic through these stubs instead.
    """
    calls = {"spoken": [], "executed": [], "email_calendar": [], "listen": [],
             "deleted_ids": [], "server_started": []}

    stubs = {
        "server": _module("server", broadcast=lambda *a, **k: None,
                          start=lambda: calls["server_started"].append(True)),
        "voice": _module(
            "voice",
            speak=lambda text: calls["spoken"].append(text),
            listen=lambda: calls["listen"].pop(0) if calls["listen"] else "",
        ),
        "brain": _module("brain", think=lambda command: ("", None, None),
                         groq_key_problem=lambda: None),
        "actions": _module(
            "actions",
            execute=lambda a, p=None: calls["executed"].append((a, p)) or True,
            handle_email_calendar=lambda a, p: calls["email_calendar"].append((a, p)) or (True, "done"),
            SIMPLE_ACTIONS={"system_sleep": None, "system_restart": None,
                            "system_shutdown": None, "screenshot": None},
            DANGEROUS_ACTIONS={"system_restart", "system_shutdown", "system_sleep"},
            is_blocked_app=lambda name: False,
        ),
        "calendar_agent": _module(
            "calendar_agent",
            find_event_by_name=lambda name: (None, "not found"),
            delete_event_by_id=lambda event_id, title: calls["deleted_ids"].append(event_id)
                                                     or (True, f"Removed {title}"),
        ),
    }
    for name, mod in stubs.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.delitem(sys.modules, "main", raising=False)

    import main
    main._test_calls = calls
    yield main
    sys.modules.pop("main", None)


@pytest.fixture
def load_brain(monkeypatch):
    """Import brain.py fresh with a chosen GROQ_API_KEY (None = unset).
    A real .env is never read, and conversation memory starts empty."""
    import dotenv
    import memory
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    memory.forget()

    def _load(key):
        if key is None:
            monkeypatch.delenv("GROQ_API_KEY", raising=False)
        else:
            monkeypatch.setenv("GROQ_API_KEY", key)
        monkeypatch.delitem(sys.modules, "brain", raising=False)
        import brain
        return brain

    yield _load
    sys.modules.pop("brain", None)
    memory.forget()
