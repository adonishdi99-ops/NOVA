"""C2: LLM-chosen app names never reach a shell, and only known apps run."""
import sys
import types

import pytest


@pytest.fixture
def actions_mod(monkeypatch):
    # actions.py imports the Google agents at module level; they aren't under test.
    gmail = types.ModuleType("gmail_agent")
    for fn in ("get_unread_emails", "read_latest_email", "send_email"):
        setattr(gmail, fn, lambda *a, **k: None)
    cal = types.ModuleType("calendar_agent")
    for fn in ("get_today_events", "get_upcoming_events", "create_event",
               "delete_event", "get_events_in_range", "delete_events_by_date"):
        setattr(cal, fn, lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "gmail_agent", gmail)
    monkeypatch.setitem(sys.modules, "calendar_agent", cal)
    monkeypatch.delitem(sys.modules, "actions", raising=False)
    import actions

    spawned = []

    class Result:
        returncode = 1

    def fake_popen(args, **kwargs):
        spawned.append(("popen", args, kwargs))
    def fake_run(args, **kwargs):
        spawned.append(("run", args, kwargs))
        return Result()
    def fake_startfile(path):
        spawned.append(("startfile", path, {}))

    monkeypatch.setattr(actions.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(actions.subprocess, "run", fake_run)
    monkeypatch.setattr(actions.os, "startfile", fake_startfile, raising=False)
    monkeypatch.setattr(actions, "APP_DB", {"spotify": r"C:\fake\Spotify.lnk"})
    monkeypatch.setattr(actions, "RAPIDFUZZ_OK", False)
    actions._spawned = spawned
    yield actions
    sys.modules.pop("actions", None)


INJECTIONS = [
    "zzqx & calc", "notepad | whoami", "x && del /q c:\\", "a; Remove-Item -Recurse",
    "$(calc)", "`calc`", "x' ; calc ; '", "spotify\ncalc", "%comspec%", "calc > out.txt",
    "*", "x)(y",
]


@pytest.mark.parametrize("name", INJECTIONS)
def test_open_app_rejects_metachars_and_spawns_nothing(actions_mod, name):
    assert actions_mod._open_app(name) is False
    assert actions_mod._spawned == []


@pytest.mark.parametrize("name", INJECTIONS)
def test_close_app_rejects_metachars_and_spawns_nothing(actions_mod, name):
    assert actions_mod._close_app(name) is False
    assert actions_mod._spawned == []


def test_open_unknown_app_not_on_path_is_refused(actions_mod, monkeypatch):
    monkeypatch.setattr(actions_mod.shutil, "which", lambda name: None)
    assert actions_mod._open_app("someunknownapp") is False
    assert actions_mod._spawned == []     # no `where <name>` shell call any more


def test_open_app_on_path_uses_resolved_path_without_shell(actions_mod, monkeypatch):
    monkeypatch.setattr(actions_mod.shutil, "which",
                        lambda name: r"C:\Tools\code.exe" if name == "code" else None)
    assert actions_mod._open_app("Code") is True
    kind, args, kwargs = actions_mod._spawned[0]
    assert (kind, args) == ("popen", [r"C:\Tools\code.exe"])
    assert not kwargs.get("shell")


@pytest.mark.parametrize("name", [r"c:\users\me\downloads\evil", "..\\evil", "dir/evil", "c:evil"])
def test_open_app_never_resolves_paths(actions_mod, monkeypatch, name):
    looked_up = []
    monkeypatch.setattr(actions_mod.shutil, "which", lambda n: looked_up.append(n) or "C:\\x.exe")
    assert actions_mod._open_app(name) is False
    assert looked_up == [] and actions_mod._spawned == []


@pytest.mark.parametrize("name", ["winword", "excel", "powerpnt"])
def test_office_apps_use_startfile_for_app_paths(actions_mod, name):
    assert actions_mod._open_app(name) is True
    assert actions_mod._spawned == [("startfile", name, {})]


def test_office_app_missing_returns_false(actions_mod, monkeypatch):
    def missing(path):
        raise FileNotFoundError(path)
    monkeypatch.setattr(actions_mod.os, "startfile", missing, raising=False)
    assert actions_mod._open_app("winword") is False


def test_close_unknown_app_is_refused(actions_mod):
    assert actions_mod._close_app("someunknownapp") is False
    assert actions_mod._spawned == []


def test_open_indexed_app_uses_startfile(actions_mod):
    assert actions_mod._open_app("Spotify") is True
    assert actions_mod._spawned == [("startfile", r"C:\fake\Spotify.lnk", {})]


def test_open_builtin_uses_argument_list_without_shell(actions_mod):
    assert actions_mod._open_app("calculator") is True
    kind, args, kwargs = actions_mod._spawned[0]
    assert (kind, args) == ("popen", ["calc"])
    assert not kwargs.get("shell")


def test_close_known_app_uses_argument_lists_without_shell(actions_mod):
    assert actions_mod._close_app("calculator") is False   # fake taskkill always "fails"
    calls = actions_mod._spawned
    assert calls[0][1] == ["taskkill", "/f", "/im", "Calculator.exe"]
    assert all(isinstance(args, list) and not kw.get("shell") for _, args, kw in calls)
    ps = calls[-1]
    assert ps[1][0] == "powershell"
    assert "Calculator" not in ps[1][-1]                     # title not spliced into script
    assert ps[2]["env"]["NOVA_CLOSE_TITLE"] == "Calculator"


def test_execute_open_app_with_injection_is_refused(actions_mod):
    assert actions_mod.execute("open_app", "zzqx & calc") is False
    assert actions_mod._spawned == []


def test_system_sleep_is_gated(actions_mod):
    assert "system_sleep" in actions_mod.DANGEROUS_ACTIONS


# ── Blocklist for system tools ──────────────────────────────────────────────
BLOCKED = ["logoff", "tsdiscon", "shutdown", "format", "diskpart", "bcdedit", "reg",
           "regedit", "cipher", "takeown", "icacls", "wmic", "net", "sc", "rundll32", "mshta"]


@pytest.mark.parametrize("name", BLOCKED + ["Shutdown.exe", "FORMAT.COM", "diskpart.exe", " net "])
def test_blocked_system_tools_never_launch(actions_mod, monkeypatch, name):
    looked_up = []
    monkeypatch.setattr(actions_mod.shutil, "which", lambda n: looked_up.append(n) or r"C:\Windows\System32\x.exe")
    assert actions_mod.is_blocked_app(name) is True
    assert actions_mod._open_app(name) is False
    assert looked_up == [] and actions_mod._spawned == []


def test_blocklist_overrides_builtins_and_index(actions_mod, monkeypatch):
    # regedit was a built-in, and an index entry by that name must not win either
    monkeypatch.setitem(actions_mod.APP_DB, "regedit", r"C:\fake\regedit.lnk")
    assert actions_mod._open_app("regedit") is False
    assert actions_mod._spawned == []


@pytest.mark.parametrize("name", ["notepad", "netflix", "scrcpy", "regex tool", "formatter"])
def test_similar_names_are_not_blocked(actions_mod, name):
    assert actions_mod.is_blocked_app(name) is False
