"""H1: voice.listen() must return "" on a mic timeout instead of raising."""
import sys
import types

import pytest
import speech_recognition as sr


@pytest.fixture
def voice_mod(monkeypatch):
    # voice.py initialises pygame's mixer and imports edge_tts at import time.
    mixer = types.ModuleType("pygame.mixer")
    mixer.init = lambda: None
    pygame = types.ModuleType("pygame")
    pygame.mixer = mixer
    monkeypatch.setitem(sys.modules, "pygame", pygame)
    monkeypatch.setitem(sys.modules, "pygame.mixer", mixer)
    monkeypatch.setitem(sys.modules, "edge_tts", types.ModuleType("edge_tts"))
    monkeypatch.delitem(sys.modules, "voice", raising=False)

    class FakeMic:
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    monkeypatch.setattr(sr, "Microphone", FakeMic)
    monkeypatch.setattr(sr.Recognizer, "adjust_for_ambient_noise", lambda self, s, duration=1: None)
    import voice
    yield voice
    sys.modules.pop("voice", None)


def test_listen_timeout_returns_empty_string(voice_mod, monkeypatch):
    def timeout(self, source, timeout=None, phrase_time_limit=None):
        raise sr.WaitTimeoutError("listening timed out while waiting for phrase to start")
    monkeypatch.setattr(sr.Recognizer, "listen", timeout)
    assert voice_mod.listen() == ""


def test_listen_mic_open_failure_returns_empty_string(voice_mod, monkeypatch):
    class BrokenMic:
        def __enter__(self): raise OSError("No Default Input Device Available")
        def __exit__(self, *exc): return False
    monkeypatch.setattr(sr, "Microphone", BrokenMic)
    assert voice_mod.listen() == ""


def test_listen_returns_lowercased_text(voice_mod, monkeypatch):
    monkeypatch.setattr(sr.Recognizer, "listen", lambda self, s, timeout=None, phrase_time_limit=None: "audio")
    monkeypatch.setattr(sr.Recognizer, "recognize_google", lambda self, audio: "Open Spotify")
    assert voice_mod.listen() == "open spotify"
