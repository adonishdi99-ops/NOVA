import speech_recognition as sr
import pyttsx3

engine = pyttsx3.init()

def speak(text):
    print("==========")
    print("SPEAK FUNCTION CALLED")
    print("TEXT:", text)

    engine.say(text)
    engine.runAndWait()

    print("SPEAK FINISHED")
    print("==========")

def listen():
    r = sr.Recognizer()

    with sr.Microphone() as source:
        print("Listening...")
        audio = r.listen(source)

    try:
        text = r.recognize_google(audio)
        print("You said:", text)
        return text.lower()

    except Exception as e:
        print("Recognition failed:", e)
        return ""