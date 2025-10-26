import whisper
import sounddevice as sd
import numpy as np
import wavio

# Record 5 seconds of audio
print("🎙️ Speak now...")
fs = 16000
duration = 5
recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
sd.wait()

# Save the audio
wavio.write("input.wav", recording, fs, sampwidth=2)
print("✅ Audio saved as input.wav")

# Load Whisper model
model = whisper.load_model("small")  # options: tiny, base, small, medium, large

# Transcribe
print("🧠 Transcribing...")
result = model.transcribe("input.wav")
print("🗣️ You said:", result["text"])
