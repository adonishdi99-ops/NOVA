import pyttsx3

engine = pyttsx3.init()

voices = engine.getProperty('voices')
print("Voices found:", len(voices))

engine.say("Hello. This is a speech test.")
engine.runAndWait()