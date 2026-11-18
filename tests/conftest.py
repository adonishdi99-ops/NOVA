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

    server/voice/brain/actions need a WebSocket loop, mic + speakers, a Groq
    key and Windows. Tests drive main's logic through these stubs instead.
    """
    calls = {"spoken": [], "executed": [], "email_calendar": [], "listen": []}

    stubs = {
        "server": _module("server", broadcast=lambda *a, **k: None),
        "voice": _module(
            "voice",
            speak=lambda text: calls["spoken"].append(text),
            listen=lambda: calls["listen"].pop(0) if calls["listen"] else "",
        ),
        "brain": _module("brain", think=lambda command: ("", None, None)),
        "actions": _module(
            "actions",
            execute=lambda a, p=None: calls["executed"].append((a, p)) or True,
            handle_email_calendar=lambda a, p: calls["email_calendar"].append((a, p)) or (True, "done"),
            SIMPLE_ACTIONS={"system_sleep": None, "system_restart": None,
                            "system_shutdown": None, "screenshot": None},
            DANGEROUS_ACTIONS={"system_restart", "system_shutdown", "system_sleep"},
        ),
    }
    for name, mod in stubs.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.delitem(sys.modules, "main", raising=False)

    import main
    main._test_calls = calls
    yield main
    sys.modules.pop("main", None)
