import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write

fs = 44100
seconds = 5

print("Recording...")

recording = sd.rec(
    int(seconds * fs),
    samplerate=fs,
    channels=1,
    dtype='float32'
)

sd.wait()

# Convert to 16-bit PCM
recording = np.int16(recording * 32767)

write("test_pcm.wav", fs, recording)

print("Saved as test_pcm.wav")