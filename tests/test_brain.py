"""M5 (Groq timeouts, retries, rate limits, history rollback, content=None)
and M1 (strict ##ACTION## tag parsing)."""
import types

import groq
import httpx
import pytest

REQ = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


class FakeCompletions:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        msg = types.SimpleNamespace(content=self.outcome)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


@pytest.fixture
def brain(load_brain):
    return load_brain("gsk_test_dummy_value")


def use_reply(brain, outcome):
    completions = FakeCompletions(outcome)
    brain.client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=completions))
    return completions


# ── M5 ──────────────────────────────────────────────────────────────────────
def test_client_has_short_timeout_and_limited_retries(brain):
    assert brain.client.timeout == brain.GROQ_TIMEOUT_S == 15.0
    assert brain.client.max_retries == brain.GROQ_MAX_RETRIES == 1


@pytest.mark.parametrize("error, spoken", [
    (groq.RateLimitError("Rate limit reached", response=httpx.Response(429, request=REQ), body=None),
     "I'm being rate limited by Groq right now. Please try again in a minute."),
    (groq.APITimeoutError(request=REQ),
     "My brain took too long to answer. Please try again."),
    (groq.APIConnectionError(request=REQ),
     "I couldn't reach my brain right now."),
    (groq.InternalServerError("boom", response=httpx.Response(500, request=REQ), body=None),
     "I couldn't reach my brain right now."),
])
def test_failed_call_gives_distinct_message_and_leaves_history_untouched(brain, error, spoken):
    import memory
    memory.remember("user", "earlier question")
    memory.remember("assistant", "earlier answer")
    use_reply(brain, error)
    assert brain.think("open spotify") == (spoken, None, None)
    assert [m["content"] for m in memory.recall()] == ["earlier question", "earlier answer"]


@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_content_is_handled_and_not_stored(brain, content):
    import memory
    use_reply(brain, content)
    assert brain.think("hello") == (
        "I didn't get an answer from my brain. Please try again.", None, None)
    assert memory.recall() == []


def test_success_stores_user_and_assistant_turns(brain):
    import memory
    use_reply(brain, '"Opening Spotify." ##ACTION:open_app:spotify##')
    assert brain.think("open spotify") == ('"Opening Spotify."', "open_app", "spotify")
    assert [m["role"] for m in memory.recall()] == ["user", "assistant"]


def test_history_window_still_sends_ten_turns_ending_with_new_command(brain):
    import memory
    for i in range(20):
        memory.remember("user" if i % 2 == 0 else "assistant", f"m{i}")
    completions = use_reply(brain, "Hi.")
    brain.think("newest")
    sent = completions.calls[0]["messages"]
    assert sent[0]["role"] == "system"
    assert len(sent) == 1 + brain.MAX_HISTORY
    assert sent[-1] == {"role": "user", "content": "newest"}


# ── M1 ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("reply, expected", [
    ('"Opening Spotify." ##ACTION:open_app:spotify##', ('"Opening Spotify."', "open_app", "spotify")),
    # text after the closing ## is dropped, not glued onto the param
    ('"Opening." ##ACTION:open_app:spotify## Enjoy your music!', ('"Opening."', "open_app", "spotify")),
    # name is stripped and lower-cased
    ('"Opening." ##ACTION: Open_App :spotify##', ('"Opening."', "open_app", "spotify")),
    ('"Taking one." ##ACTION:SCREENSHOT##', ('"Taking one."', "screenshot", None)),
    # params may contain ':' and '|'
    ('Opening. ##ACTION:open_website:https://reddit.com/r/python##', ("Opening.", "open_website", "https://reddit.com/r/python")),
    ('Adding it. ##ACTION:calendar_create:call mum|2026-11-21|09:00|1##',
     ("Adding it.", "calendar_create", "call mum|2026-11-21|09:00|1")),
    # tag first: no spoken text, trailing words are not the action name
    ('##ACTION:system_restart## Restarting now.', ("", "system_restart", None)),
    # only the first of several tags counts
    ('"Two things." ##ACTION:volume_up:20## ##ACTION:screenshot##', ('"Two things."', "volume_up", "20")),
    # empty param -> None
    ('"Removing it." ##ACTION:calendar_delete: ##', ('"Removing it."', "calendar_delete", None)),
    # filtered fake action names
    ('"Okay." ##ACTION:none##', ('"Okay."', None, None)),
    ('"Okay." ##ACTION:Open_Browser:x##', ('"Okay."', None, None)),
    # plain answers pass through
    ("Paris is the capital of France.", ("Paris is the capital of France.", None, None)),
])
def test_parse_reply(brain, reply, expected):
    assert brain.parse_reply(reply) == expected


@pytest.mark.parametrize("reply", [
    '"Opening." ##ACTION:open_app:spotify',     # never closed
    '"Opening." ##ACTION:##',                    # no name
    '"Opening." ##ACTION:open app:spotify##',    # space inside name
])
def test_malformed_tags_give_no_action_and_are_not_spoken(brain, reply):
    spoken, action, param = brain.parse_reply(reply)
    assert (spoken, action, param) == ('"Opening."', None, None)


def test_extra_tags_and_trailing_text_are_logged(brain, capsys):
    brain.parse_reply('Ok. ##ACTION:volume_up:20## then ##ACTION:screenshot## bye')
    out = capsys.readouterr().out
    assert "Ignoring extra action tags: ['##ACTION:screenshot##']" in out
    assert "Dropped text after action tag" in out
