# main.py
import os
import time
import threading
import webbrowser
import server
from voice import speak, listen
from brain import think
from actions import execute, handle_email_calendar, SIMPLE_ACTIONS, DANGEROUS_ACTIONS

SHUTDOWN_PHRASES = [
    "shut down nova", "shutdown nova",
    "goodbye nova",   "good bye nova",
    "bye nova",       "bye bye nova",
    "nova goodbye",   "nova bye",
    "nova off",       "nova shut down",
    "turn off nova",  "exit nova",
    "quit nova",      "stop nova",
    "farewell nova",
]

EMAIL_CALENDAR_ACTIONS = {
    "email_unread", "email_read", "email_send",
    "calendar_today", "calendar_upcoming", "calendar_range",
    "calendar_create", "calendar_delete", "calendar_delete_date",
}

DELETE_ACTIONS   = {"calendar_delete", "calendar_delete_date"}
DANGEROUS_LABELS = {
    "system_restart":  "restart your PC",
    "system_shutdown": "shut down your PC",
}

KNOWN_ACTIONS = (
    set(SIMPLE_ACTIONS.keys()) |
    {
        "open_app", "close_app",
        "open_website",
        "search_google", "search_youtube",
        "shutdown", "volume_up", "volume_down", "set_volume",
    } |
    EMAIL_CALENDAR_ACTIONS
)

CONFIRM_WORDS = {
    "yes", "yeah", "yep", "confirm", "do it",
    "go ahead", "sure", "correct", "right", "proceed", "okay",
}


def wants_shutdown(command: str) -> bool:
    cmd = command.lower()
    if any(phrase in cmd for phrase in SHUTDOWN_PHRASES):
        return True
    has_bye  = any(w in cmd.split() for w in ["bye", "goodbye"])
    has_name = "nova" in cmd
    return has_bye and has_name


def nova_speak(text: str):
    server.broadcast("SPEAKING", text)
    speak(text)
    server.broadcast("IDLE")


def ask_confirm(prompt: str) -> bool:
    nova_speak(prompt)
    server.broadcast("LISTENING")
    response = listen()
    confirmed = any(w in response for w in CONFIRM_WORDS)
    if not confirmed:
        nova_speak("Cancelled.")
    return confirmed


def run():
    server.start()
    ui_path = os.path.abspath("ui.html")
    webbrowser.open(f"file:///{ui_path}")

    # True while a command is being processed/spoken, so the voice thread
    # doesn't pick NOVA's own speech back up (or fight with typed input).
    busy = threading.Event()
    threading.Thread(target=_voice_loop, args=(busy,), daemon=True).start()

    nova_speak("Nova online")

    while True:
        command = server.COMMAND_QUEUE.get()  # blocks until voice OR typed input arrives
        if not command:
            continue

        busy.set()
        try:
            should_stop = _handle_command(command)
        finally:
            busy.clear()

        if should_stop:
            break


def _voice_loop(busy: threading.Event):
    """Runs on a background thread. Keeps listening on the mic (unless muted
    or a command is currently being processed) and drops recognized speech
    onto the same queue typed commands go into."""
    while True:
        if server.is_muted():
            server.broadcast("MUTED")
            time.sleep(0.25)
            continue

        if busy.is_set():
            time.sleep(0.1)
            continue

        server.broadcast("LISTENING")
        try:
            command = listen()
        except Exception:
            continue

        if command:
            server.COMMAND_QUEUE.put(command)


def _handle_command(command: str) -> bool:
    """Processes one command from either input source. Returns True if
    NOVA should shut down after this."""
    if wants_shutdown(command):
        nova_speak("Shutting down. Goodbye.")
        return True

    server.broadcast("PROCESSING", command)
    spoken, action, param = think(command)

    if action == "shutdown":
        nova_speak("Shutting down. Goodbye.")
        return True

    if spoken:
        nova_speak(spoken)

    if not action:
        return False

    if action not in KNOWN_ACTIONS:
        print(f"[main] Ignoring unknown action: {action}")
        return False

    # ── Confirmation gates ──────────────────────────────────────────────
    if action in DANGEROUS_ACTIONS:
        label = DANGEROUS_LABELS.get(action, action)
        if not ask_confirm(f"Are you sure you want to {label}?"):
            return False

    elif action in DELETE_ACTIONS:
        if action == "calendar_delete":
            prompt = f"Are you sure you want to delete '{param}' from your calendar?"
        else:
            prompt = f"Are you sure you want to delete all events on {param}?"
        if not ask_confirm(prompt):
            return False

    # ── Execute ─────────────────────────────────────────────────────────
    if action in EMAIL_CALENDAR_ACTIONS:
        server.broadcast("PROCESSING")
        success, result = handle_email_calendar(action, param)
        if result:
            nova_speak(result)
        elif not success:
            nova_speak("I wasn't able to complete that.")
    else:
        success = execute(action, param)
        if not success:
            if action == "open_app":
                nova_speak(f"I couldn't find {param or 'that app'} on your computer.")
            elif action == "close_app":
                nova_speak(f"I couldn't close {param or 'that app'}.")
            else:
                nova_speak("I wasn't able to complete that action.")

    return False


if __name__ == "__main__":
    run()