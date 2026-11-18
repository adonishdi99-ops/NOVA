# brain.py
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from groq import Groq
from memory import remember, recall

load_dotenv()

GROQ_API_KEY      = (os.getenv("GROQ_API_KEY") or "").strip()
_KEY_PLACEHOLDERS = {"", "your_groq_api_key_here"}


def groq_key_problem():
    """None if GROQ_API_KEY looks usable, otherwise a message saying how to fix it."""
    if GROQ_API_KEY in _KEY_PLACEHOLDERS:
        return ("GROQ_API_KEY is not set. Copy .env.example to .env in the NOVA folder, "
                "put your key from https://console.groq.com/keys after GROQ_API_KEY=, "
                "then start NOVA again.")
    return None


# Created only with a usable key, so importing brain never crashes; main.run()
# reports the problem via groq_key_problem() before anything else starts.
client    = None if groq_key_problem() else Groq(api_key=GROQ_API_KEY)
USER_NAME = os.getenv("USER_NAME", "Boss")
MAX_HISTORY = 10

# llama-3.3-70b-versatile was deprecated by Groq (June 2026).
# openai/gpt-oss-120b is the recommended replacement - strong at
# instruction-following / tool-use, similar tier to the old 70b model.
MODEL = "openai/gpt-oss-120b"


def _build_system_prompt():
    now      = datetime.now()
    today    = now.strftime("%A, %B %d, %Y")
    time_now = now.strftime("%I:%M %p")
    date_iso = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    return f"""You are Nova, a smart personal voice assistant for {USER_NAME} on Windows.
Today is {today}. Current time is {time_now}.
Today's date: {date_iso}. Tomorrow's date: {tomorrow}.

━━━ ACTION TAG FORMAT — READ THIS FIRST ━━━
When performing an action, your response must follow this EXACT pattern:

  "Short spoken phrase." ##ACTION:action_name##
  "Short spoken phrase." ##ACTION:action_name:param##

The tag goes at the END of your reply. One short sentence, then the tag. Nothing else.

✅ CORRECT EXAMPLES — copy this format exactly:

  User: "check my emails"
  You:  "Checking your emails." ##ACTION:email_unread##

  User: "what's on my calendar today"
  You:  "Checking today's calendar." ##ACTION:calendar_today##

  User: "what's on my calendar tomorrow"
  You:  "Checking your upcoming events." ##ACTION:calendar_upcoming##

  User: "take a screenshot"
  You:  "Taking a screenshot." ##ACTION:screenshot##

  User: "open settings"
  You:  "Opening Settings." ##ACTION:open_settings##

  User: "open Spotify"
  You:  "Opening Spotify." ##ACTION:open_app:spotify##

  User: "close calculator"
  You:  "Closing the calculator." ##ACTION:close_app:calculator##

  User: "search YouTube for Wizkid"
  You:  "Searching YouTube for Wizkid." ##ACTION:search_youtube:Wizkid##

  User: "remind me to call mum tomorrow at 9am"
  You:  "Adding that to your calendar." ##ACTION:calendar_create:call mum|{tomorrow}|09:00|1##

  User: "delete drink water"
  You:  "Removing that from your calendar." ##ACTION:calendar_delete:drink water##

❌ WRONG — never do this:

  User: "what's on my calendar tomorrow"
  You:  "You have a gym session at 10am." ← HALLUCINATED, NO TAG

  User: "check my emails"
  You:  "Checking your emails..." ← SPOKEN ONLY, NO TAG

  User: "what's on my calendar tomorrow"
  You:  "Checking your calendar... You have a meeting at 2pm." ← BOTH WRONG

━━━ AVAILABLE ACTIONS ━━━
Format: ##ACTION:name## or ##ACTION:name:param##

[Apps & Web]
  open_app:APP_NAME       ##ACTION:open_app:spotify##
  close_app:APP_NAME      ##ACTION:close_app:calculator##
  open_website:URL        ##ACTION:open_website:reddit.com##
  search_google:QUERY     ##ACTION:search_google:Premier League table##
  search_youtube:QUERY    ##ACTION:search_youtube:Burna Boy##
  open_youtube | open_google | open_settings

[Volume]
  volume_up:PERCENT | volume_down:PERCENT | set_volume:PERCENT | volume_mute

[System]
  screenshot | system_sleep | system_restart | system_shutdown

[Email]
  email_unread | email_read | email_send:TO|SUBJECT|BODY

[Calendar]
  calendar_today | calendar_upcoming | calendar_range:YYYY-MM-DD|YYYY-MM-DD
  calendar_create:EVENT_NAME|YYYY-MM-DD|HH:MM|DURATION_HOURS
  calendar_delete:EVENT_NAME | calendar_delete_date:YYYY-MM-DD

━━━ CALENDAR & EMAIL RULES ━━━
- You have ZERO knowledge of {USER_NAME}'s calendar or emails. Always tag the action.
- "What's on my calendar" → ##ACTION:calendar_today## or ##ACTION:calendar_upcoming##
- "Remind me to X at Y" → ##ACTION:calendar_create:X|DATE|TIME|1## — ALWAYS, never filter
- "Set alarm for Y"     → ##ACTION:calendar_create:Alarm|DATE|TIME|1##
- Dates: YYYY-MM-DD. Times: HH:MM (24-hour). "tomorrow" = {tomorrow}.
- NEVER ask for verbal confirmation on delete — the system handles it.
- NEVER invent calendar events or email content.

━━━ FAKE ACTION NAMES — NEVER USE THESE ━━━
none | null | remind | alarm | query | calendar_update | open_browser

━━━ GENERAL QUESTIONS ━━━
Answer conversational and knowledge questions directly from your own knowledge.
Be confident and concise. For things you don't know, say so briefly.
"""


def think(command: str):
    if client is None:
        return "My Groq API key isn't set, so I can't think right now.", None, None
    try:
        remember("user", command)

        history  = recall()[-MAX_HISTORY:]
        messages = [{"role": "system", "content": _build_system_prompt()}] + history

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages
        )

        full_reply = response.choices[0].message.content.strip()
        remember("assistant", full_reply)

        action_name  = None
        action_param = None
        spoken       = full_reply

        if "##ACTION:" in full_reply:
            parts  = full_reply.split("##ACTION:")
            spoken = parts[0].strip()
            raw    = parts[1].replace("##", "").strip()

            if ":" in raw:
                action_name, action_param = raw.split(":", 1)
            else:
                action_name = raw

            FAKE_ACTIONS = {
                "none", "null", "", "remind", "alarm", "query",
                "calendar_update", "change_system_color",
                "available_actions", "open_browser",
            }
            if action_name and action_name.lower() in FAKE_ACTIONS:
                print(f"[brain] Filtered hallucinated action: {action_name}")
                action_name  = None
                action_param = None

        return spoken, action_name, action_param

    except Exception as e:
        print("BRAIN ERROR:", e)
        return "I couldn't reach my brain right now.", None, None