# actions.py
import os
import time
import shutil
import subprocess
import webbrowser
import ctypes
import urllib.parse
from pathlib import Path

# ── Volume via pycaw ──────────────────────────────────────────────────────────
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    _devices   = AudioUtilities.GetSpeakers()
    _interface = _devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    _vol_ctrl  = cast(_interface, POINTER(IAudioEndpointVolume))
    PYCAW_OK   = True
except Exception as e:
    print(f"[actions] pycaw unavailable: {e}")
    PYCAW_OK = False

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP   = 0xAF

def _press_key(vk, times=1):
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0x0000, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)

def _get_vol():
    return _vol_ctrl.GetMasterVolumeLevelScalar() if PYCAW_OK else 0.5

def _set_vol(scalar):
    if PYCAW_OK:
        _vol_ctrl.SetMasterVolumeLevelScalar(max(0.0, min(1.0, scalar)), None)

def _vol_up(amount=20):
    if PYCAW_OK: _set_vol(_get_vol() + amount / 100)
    else:        _press_key(VK_VOLUME_UP, max(1, amount // 2))

def _vol_down(amount=20):
    if PYCAW_OK: _set_vol(_get_vol() - amount / 100)
    else:        _press_key(VK_VOLUME_DOWN, max(1, amount // 2))

def _vol_set(level):
    if PYCAW_OK: _set_vol(level / 100)
    else:
        _press_key(VK_VOLUME_UP, 50)
        _press_key(VK_VOLUME_DOWN, max(0, (100 - level) // 2))

def _vol_mute():
    if PYCAW_OK: _vol_ctrl.SetMute(not _vol_ctrl.GetMute(), None)
    else:        _press_key(VK_VOLUME_MUTE)


# ── App launcher — Start Menu database + rapidfuzz ────────────────────────────
try:
    from rapidfuzz import process as fuzz_process
    RAPIDFUZZ_OK = True
except ImportError:
    print("[actions] rapidfuzz not installed — run: pip install rapidfuzz")
    RAPIDFUZZ_OK = False

_START_MENU_PATHS = [
    Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
    Path.home() / r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs",
]

_EXTRA_PATHS = {
    "spotify": [
        Path(os.environ.get("APPDATA", "")) / "Spotify" / "Spotify.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Spotify" / "Spotify.exe",
    ],
    "discord": [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Discord" / "Update.exe",
        Path(os.environ.get("APPDATA", "")) / "Discord" / "Discord.exe",
    ],
}

_BUILTINS = {
    "calc", "notepad", "mspaint", "cmd", "explorer",
    "taskmgr", "regedit", "msconfig", "winword", "excel", "powerpnt",
}
# Office apps registered under App Paths rather than PATH.
_APP_PATHS_BUILTINS = {"winword", "excel", "powerpnt"}
_BUILTIN_MAP = {
    "calculator": "calc",
    "paint":      "mspaint",
}

_PROCESS_MAP = {
    "calculator":     ["Calculator.exe", "CalculatorApp.exe", "calc.exe"],
    "calc":           ["Calculator.exe", "CalculatorApp.exe", "calc.exe"],
    "notepad":        ["notepad.exe"],
    "spotify":        ["Spotify.exe"],
    "discord":        ["Discord.exe"],
    "chrome":         ["chrome.exe"],
    "firefox":        ["firefox.exe"],
    "edge":           ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "vlc":            ["vlc.exe"],
    "word":           ["WINWORD.EXE"],
    "excel":          ["EXCEL.EXE"],
    "powerpoint":     ["POWERPNT.EXE"],
    "paint":          ["mspaint.exe"],
    "task manager":   ["Taskmgr.exe"],
    "steam":          ["steam.exe"],
    "whatsapp":       ["WhatsApp.exe"],
    "teams":          ["Teams.exe"],
    "zoom":           ["Zoom.exe"],
}


def _build_app_db():
    apps = {}
    for folder in _START_MENU_PATHS:
        if folder.exists():
            for shortcut in folder.rglob("*.lnk"):
                name = shortcut.stem.lower().strip()
                if name:
                    apps[name] = str(shortcut)
    for name, paths in _EXTRA_PATHS.items():
        for p in paths:
            if p.exists():
                apps[name] = str(p)
                break
    print(f"[actions] App database: {len(apps)} apps indexed")
    return apps


APP_DB = _build_app_db()

# Characters with special meaning to cmd.exe or PowerShell. App names come from
# the LLM, so a name containing any of these is refused outright.
_SHELL_METACHARS = set('&|<>^%"\'`;$(){}[]*?!\n\r')


def has_shell_metachars(name: str) -> bool:
    return any(c in _SHELL_METACHARS for c in name)


def _is_known_app(name: str) -> bool:
    """Only names from the app index or the hard-coded maps may be launched or killed."""
    return (name in APP_DB or name in _BUILTIN_MAP
            or name in _BUILTINS or name in _PROCESS_MAP)


def _open_app(app_name: str) -> bool:
    name = app_name.lower().strip()

    if not name or has_shell_metachars(name):
        print(f"[actions] Rejected app name: {app_name!r}")
        return False

    if name in APP_DB:
        os.startfile(APP_DB[name])
        print(f"[actions] Exact: '{name}'")
        return True

    if RAPIDFUZZ_OK and APP_DB:
        result = fuzz_process.extractOne(name, APP_DB.keys(), score_cutoff=75)
        if result:
            matched, score, _ = result
            os.startfile(APP_DB[matched])
            print(f"[actions] Fuzzy: '{name}' → '{matched}' ({score:.0f})")
            return True

    cmd = _BUILTIN_MAP.get(name, name)
    if cmd in _APP_PATHS_BUILTINS:
        # Office isn't on PATH; ShellExecute (os.startfile) resolves it via App Paths.
        try:
            os.startfile(cmd)
            return True
        except OSError as e:
            print(f"[actions] Could not start '{cmd}': {e}")
            return False
    if cmd in _BUILTINS:
        subprocess.Popen([cmd])
        return True

    # Anything else on PATH: resolve it ourselves and launch with no shell.
    # Bare names only, so the LLM can't point at an arbitrary file path.
    if not any(sep in name for sep in ("/", "\\", ":")):
        path = shutil.which(name)
        if path:
            subprocess.Popen([path])
            print(f"[actions] PATH: '{name}' → {path}")
            return True

    print(f"[actions] Not found: '{name}'")
    return False


def _close_app(app_name: str) -> bool:
    name = app_name.lower().strip()

    if not name or has_shell_metachars(name) or not _is_known_app(name):
        print(f"[actions] Rejected app name for close: {app_name!r}")
        return False

    candidates = _PROCESS_MAP.get(name, [f"{name}.exe"])

    # Strategy 1: kill by process name
    for exe in candidates:
        result = subprocess.run(
            ["taskkill", "/f", "/im", exe], capture_output=True
        )
        if result.returncode == 0:
            print(f"[actions] Closed by process: {exe}")
            return True

    # Strategy 2: kill by window title (UWP apps)
    title = name.title()
    result = subprocess.run(
        ["taskkill", "/f", "/fi", f"WINDOWTITLE eq {title}"],
        capture_output=True
    )
    if result.returncode == 0:
        print(f"[actions] Closed by title: '{title}'")
        return True

    # Strategy 3: PowerShell Stop-Process by partial window title.
    # The title is passed in an environment variable, never spliced into the script.
    ps_script = (
        "Get-Process | Where-Object { $_.MainWindowTitle -like "
        "('*' + $env:NOVA_CLOSE_TITLE + '*') } | Stop-Process -Force"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, env={**os.environ, "NOVA_CLOSE_TITLE": title},
    )
    if result.returncode == 0:
        print(f"[actions] Closed via PowerShell: '{title}'")
        return True

    print(f"[actions] Could not close: '{name}'")
    return False


# ── Web & Search ───────────────────────────────────────────────────────────────
def _open_website(url: str) -> bool:
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return True

def _search_google(query: str) -> bool:
    webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
    return True

def _search_youtube(query: str) -> bool:
    webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}")
    return True


# ── Screenshot — Win+Shift+S keyboard shortcut ────────────────────────────────
def _screenshot() -> bool:
    """Simulate Win+Shift+S to open the Snipping Tool overlay."""
    VK_LWIN  = 0x5B
    VK_SHIFT = 0x10
    VK_S     = 0x53
    KEYDOWN  = 0
    KEYUP    = 2

    ctypes.windll.user32.keybd_event(VK_LWIN,  0, KEYDOWN, 0)
    ctypes.windll.user32.keybd_event(VK_SHIFT, 0, KEYDOWN, 0)
    ctypes.windll.user32.keybd_event(VK_S,     0, KEYDOWN, 0)
    time.sleep(0.05)
    ctypes.windll.user32.keybd_event(VK_S,     0, KEYUP,   0)
    ctypes.windll.user32.keybd_event(VK_SHIFT, 0, KEYUP,   0)
    ctypes.windll.user32.keybd_event(VK_LWIN,  0, KEYUP,   0)
    return True


# ── System ────────────────────────────────────────────────────────────────────
def _sleep():         os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0"); return True
def _restart():       os.system("shutdown /r /t 5"); return True
def _shutdown_pc():   os.system("shutdown /s /t 5"); return True
def _open_settings(): os.system("start ms-settings:"); return True


# ── Action registry ────────────────────────────────────────────────────────────
SIMPLE_ACTIONS = {
    "open_youtube":    lambda: webbrowser.open("https://youtube.com") or True,
    "open_google":     lambda: webbrowser.open("https://google.com") or True,
    "volume_mute":     _vol_mute,
    "screenshot":      _screenshot,
    "system_sleep":    _sleep,
    "system_restart":  _restart,
    "system_shutdown": _shutdown_pc,
    "open_settings":   _open_settings,
}

DANGEROUS_ACTIONS = {"system_restart", "system_shutdown", "system_sleep"}


def execute(action_name: str, param=None) -> bool:
    if action_name == "open_app"       and param: return _open_app(param)
    if action_name == "close_app"      and param: return _close_app(param)
    if action_name == "open_website"   and param: return _open_website(param)
    if action_name == "search_google"  and param: return _search_google(param)
    if action_name == "search_youtube" and param: return _search_youtube(param)
    if action_name == "volume_up":
        amount = int(param) if param and str(param).isdigit() else 20
        _vol_up(amount); return True
    if action_name == "volume_down":
        amount = int(param) if param and str(param).isdigit() else 20
        _vol_down(amount); return True
    if action_name == "set_volume":
        level = int(param) if param and str(param).isdigit() else 50
        _vol_set(level); return True
    if action_name in SIMPLE_ACTIONS:
        result = SIMPLE_ACTIONS[action_name]()
        return result is not False
    print(f"[actions] Unknown action: {action_name}")
    return False


# ── Email & Calendar ───────────────────────────────────────────────────────────
from gmail_agent    import get_unread_emails, read_latest_email, send_email
from calendar_agent import (get_today_events, get_upcoming_events,
                             create_event, delete_event,
                             get_events_in_range, delete_events_by_date)


def handle_email_calendar(action_name: str, param):
    try:
        if action_name == "email_unread":
            return True, get_unread_emails()
        if action_name == "email_read":
            return True, read_latest_email()
        if action_name == "email_send" and param:
            parts = param.split("|", 2)
            if len(parts) < 3:
                return False, "I need a recipient, subject, and message to send an email."
            to, subject, body = parts
            return True, send_email(to.strip(), subject.strip(), body.strip())
        if action_name == "calendar_today":
            return True, get_today_events()
        if action_name == "calendar_upcoming":
            return True, get_upcoming_events()
        if action_name == "calendar_range" and param:
            parts = param.split("|")
            start = parts[0].strip() if len(parts) > 0 else None
            end   = parts[1].strip() if len(parts) > 1 else None
            return True, get_events_in_range(start, end)
        if action_name == "calendar_create" and param:
            parts = param.split("|")
            if len(parts) < 3:
                return False, "I need an event name, date, and time to create an event."
            title    = parts[0].strip()
            date_str = parts[1].strip()
            time_str = parts[2].strip()
            duration = parts[3].strip() if len(parts) > 3 else "1"
            return True, create_event(title, date_str, time_str, duration)
        if action_name == "calendar_delete" and param:
            return True, delete_event(param.strip())
        if action_name == "calendar_delete_date" and param:
            return True, delete_events_by_date(param.strip())
        return False, None
    except Exception as e:
        print(f"[actions] Email/Calendar error: {e}")
        return False, "Something went wrong with that request."