# voice.py
import asyncio
import os
import tempfile
import speech_recognition as sr
import edge_tts
import pygame
import pygame.mixer

VOICE = "en-US-AriaNeural"

pygame.mixer.init()
_tmp_file = os.path.join(tempfile.gettempdir(), "nova_tts.mp3")


async def _generate(text: str):
    await edge_tts.Communicate(text, VOICE).save(_tmp_file)


def speak(text: str):
    print("Nova:", text)
    try:
        asyncio.run(_generate(text))
        pygame.mixer.music.load(_tmp_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
    except Exception as e:
        print("TTS ERROR:", e)


def listen() -> str:
    r = sr.Recognizer()
    r.pause_threshold       = 1.5
    r.non_speaking_duration = 0.6

    with sr.Microphone() as source:
        print("Listening...")
        r.adjust_for_ambient_noise(source, duration=0.5)
        audio = r.listen(source, timeout=10, phrase_time_limit=20)

    try:
        text = r.recognize_google(audio)
        print("You:", text)
        return text.lower()
    except sr.WaitTimeoutError:
        print("No speech detected")
        return ""
    except sr.UnknownValueError:
        print("Could not understand audio")
        return ""
    except Exception as e:
        print(f"[voice] Error: {e}")
        return ""