"""H6: a missing GROQ_API_KEY gives a clear startup message, not an import crash."""
import sys

import dotenv
import pytest


@pytest.fixture
def load_brain(monkeypatch):
    # Never read a real .env from disk during tests.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)

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


@pytest.mark.parametrize("key", [None, "", "   ", "your_groq_api_key_here"])
def test_missing_or_placeholder_key_is_reported_not_raised(load_brain, key):
    brain = load_brain(key)                      # used to raise GroqError here
    problem = brain.groq_key_problem()
    assert problem and "GROQ_API_KEY is not set" in problem and ".env" in problem
    assert brain.client is None
    assert brain.think("hello") == (
        "My Groq API key isn't set, so I can't think right now.", None, None)


def test_real_looking_key_creates_client(load_brain):
    brain = load_brain("gsk_test_dummy_value")
    assert brain.groq_key_problem() is None
    assert brain.client is not None


def test_main_run_exits_with_message_before_starting(main_mod, capsys):
    main_mod.groq_key_problem = lambda: "GROQ_API_KEY is not set."
    with pytest.raises(SystemExit) as exc:
        main_mod.run()
    assert exc.value.code == 1
    assert "Cannot start NOVA: GROQ_API_KEY is not set." in capsys.readouterr().err
    assert main_mod._test_calls["server_started"] == []
