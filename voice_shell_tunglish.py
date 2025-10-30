import subprocess
import json
import re
import os
import sys
import requests
import sounddevice as sd
import wavio
import google.generativeai as genai
import pyttsx3
import shlex
import numpy as np
from collections import deque
from dotenv import load_dotenv
from sarvamai import SarvamAI
import socket

# Load environment variables from .env if present
load_dotenv()

# ---------------- Gemini API Setup ----------------
genai.configure(api_key="AIzaSyBUWKcixG2e1e0w4_6h127tELGEtZx2ePw")
model_gemini = genai.GenerativeModel("models/gemini-2.5-flash")

# ---------------- Text-to-Speech Setup ----------------
engine = pyttsx3.init()
def speak(text):
    engine.say(text)
    engine.runAndWait()

# ---------------- Transcription Provider Setup ----------------
# Make Whisper optional and add Sarvam AI support via env vars.
try:
    from faster_whisper import WhisperModel as _FWWhisperModel
except ImportError:
    _FWWhisperModel = None

whisper_model = None

# Provider selection: 'sarvam' (default) or 'whisper'
TRANSCRIBE_PROVIDER = os.environ.get("TRANSCRIBE_PROVIDER", "sarvam").strip().lower()

# Sarvam AI configuration (set these env vars before running)
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "").strip()
SARVAM_STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saarika:v2.5").strip()
SARVAM_LANGUAGE_CODE = os.environ.get("SARVAM_LANGUAGE_CODE", "ta-IN").strip()

# Lazy init Sarvam client
_sarvam_client = None

# ---------------- WSL current working directory state ----------------
wsl_current_dir = None

def _get_initial_wsl_cwd():
    return windows_to_wsl_path(os.getcwd())

def _resolve_wsl_dir(base_dir, target_dir, user_opts):
    try:
        args = ["wsl"] + user_opts + ["--cd", base_dir, "--", "bash", "-lc", f"cd {shlex.quote(target_dir)} && pwd"]
        res = subprocess.run(args, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            out = res.stdout.strip()
            if out:
                return out
    except Exception:
        pass
    return base_dir

# ---------------- Voice Recording ----------------
def record_voice(fs=16000, filename="input.wav", silence_ms=800, frame_ms=50, threshold=0.01, preroll_ms=300, tail_ms=200):
    print("🎤 Listening... start speaking. I will stop when you pause.")
    frame_samples = int(fs * (frame_ms / 1000.0))
    silence_frames_needed = int(silence_ms / frame_ms)
    preroll_frames = max(1, int(preroll_ms / frame_ms))
    tail_frames = max(0, int(tail_ms / frame_ms))
    collected = []
    prebuffer = deque(maxlen=preroll_frames)
    started = False
    silent_count = 0
    with sd.InputStream(channels=1, samplerate=fs, dtype='int16') as stream:
        while True:
            data, _ = stream.read(frame_samples)
            rms = np.sqrt(np.mean((data.astype(np.float32) / 32768.0) ** 2) + 1e-12)
            if not started:
                prebuffer.append(data.copy())
                if rms >= threshold:
                    started = True
                    collected.extend(list(prebuffer))
                    prebuffer.clear()
            else:
                collected.append(data.copy())
                if rms < threshold:
                    silent_count += 1
                else:
                    silent_count = 0
                if silent_count >= silence_frames_needed:
                    # add small tail after silence
                    for _ in range(tail_frames):
                        tail_data, _ = stream.read(frame_samples)
                        collected.append(tail_data.copy())
                    break
    if not collected:
        collected = list(prebuffer)
    recording = np.concatenate(collected, axis=0) if collected else np.zeros((0, 1), dtype=np.int16)
    wavio.write(filename, recording, fs, sampwidth=2)
    print("✅ Audio saved as input.wav")

# ---------------- Transcription ----------------
def transcribe_audio(filename="input.wav"):
    # Select provider based on env var
    provider = TRANSCRIBE_PROVIDER
    if provider == "sarvam":
        return sarvam_transcribe(filename)
    elif provider == "whisper":
        return whisper_transcribe(filename)
    else:
        print(f"⚠️ Unknown TRANSCRIBE_PROVIDER='{provider}', falling back to Sarvam")
        return sarvam_transcribe(filename)

def whisper_transcribe(filename="input.wav"):
    global whisper_model
    if _FWWhisperModel is None:
        raise RuntimeError("faster-whisper is not installed. Set TRANSCRIBE_PROVIDER=sarvam or install faster-whisper.")
    if whisper_model is None:
        whisper_model = _FWWhisperModel("small", device="cpu", compute_type="float32")
    segments, info = whisper_model.transcribe(filename)
    text = " ".join([s.text for s in segments]).strip()
    print("🗣️ You said:", text)
    return text

def sarvam_transcribe(filename="input.wav"):
    global _sarvam_client
    if not SARVAM_API_KEY:
        raise RuntimeError("Set SARVAM_API_KEY in .env with your Sarvam API key.")
    if _sarvam_client is None:
        _sarvam_client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
    try:
        with open(filename, "rb") as f:
            response = _sarvam_client.speech_to_text.transcribe(
                file=f,
                model=SARVAM_STT_MODEL,
                language_code=SARVAM_LANGUAGE_CODE,
            )
    except socket.gaierror as e:
        raise RuntimeError("Network/DNS error while reaching Sarvam API. Check your internet or DNS settings.") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error while reaching Sarvam API: {e}") from e
    # Response may be dict-like or object; handle common cases
    text = None
    try:
        # If SDK returns a dict
        if isinstance(response, dict):
            text = response.get("text") or response.get("transcript") or response.get("transcription")
        else:
            # Try attributes commonly used
            text = getattr(response, "text", None) or getattr(response, "transcript", None) or getattr(response, "transcription", None)
    except Exception:
        pass
    if not text:
        text = str(response)
    text = str(text).strip()
    print("🗣️ You said:", text)
    return text

# ---------------- Tamil/Tunglish → English ----------------
def tamil_to_tunglish(text):
    prompt = f"""
Translate the following Tamil/Tunglish instruction into a clear English instruction 
that can be used for generating a Linux shell command. Do not change the meaning.

Instruction: "{text}"
"""
    try:
        response = model_gemini.generate_content(prompt)
        return response.text.strip()
    except socket.gaierror as e:
        raise RuntimeError("Network/DNS error while reaching Gemini. Check your internet or DNS settings.") from e
    except Exception as e:
        raise

# ---------------- Gemini: Command + Exit Detection ----------------
def get_command_and_exit(text):
    prompt = f"""
You are a Linux shell assistant.
- Output a single non-interactive Linux command only (no explanations).
- STRICTLY FORBIDDEN: editors/pagers or any interactive tools (nano, vi, vim, emacs, ed, less, more, man, top, htop, watch, code).
- Do NOT propose interactive redirections like 'cat > file' or here-docs.
- Use non-interactive patterns only:
  - create empty file: touch <file>
  - write text: printf %s "text" > <file>   (or echo "text" > <file>)
  - append text: printf %s "text" >> <file>
  - create directory: mkdir -p <dir>
  - copy/move/remove: cp/mv/rm without prompts; avoid flags that require interaction
- Generate exactly one line that can run in WSL.
- Do not add explanations or extra text.
Instruction: "{text}"
Determine if the user wants to exit the shell and even if the user thanks you, consider it a No. Answer Yes/No.
Respond in strict JSON:
\n  "command": "shell_command_here",\n  "exit": "Yes" or "No"\n
"""
    try:
        try:
            response = model_gemini.generate_content(prompt)
        except socket.gaierror as e:
            raise RuntimeError("Network/DNS error while reaching Gemini. Check your internet or DNS settings.") from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error while reaching Gemini: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Error generating command: {e}") from e
    
    # Extract JSON safely in case Gemini adds extra text
    try:
        text_json = re.search(r"\{.*\}", response.text, re.DOTALL)
        if text_json:
            data = json.loads(text_json.group())
        else:
            data = {}
        cmd = data.get("command", "").replace("`", "").strip()
        exit_flag = data.get("exit", "").strip().lower().startswith("yes")
    except:
        cmd = ""
        exit_flag = False
    return cmd, exit_flag

# ---------------- WSL Path Conversion ----------------
def windows_to_wsl_path(win_path):
    drive = win_path[0].lower()
    path_rest = win_path[3:].replace("\\", "/")
    return f"/mnt/{drive}/{path_rest}"

# ---------------- Execute command safely in WSL ----------------
INTERACTIVE_COMMANDS = [
    "nano", "vi", "vim", "emacs", "ed",
    "less", "more", "man",
    "top", "htop", "watch",
    "code", "notepad",
]

def sanitize_command(cmd):
    for word in INTERACTIVE_COMMANDS:
        if re.search(rf"\b{re.escape(word)}\b", cmd):
            print(f"❌ Unsafe command detected: {word}, skipping.")
            return ""
    if re.search(r"\bcat\b\s*>+\s*\S+", cmd):
        print("❌ Unsafe command detected: cat with redirection, skipping.")
        return ""
    return cmd.strip()

def execute_in_wsl(command, timeout=10):
    if not command:
        return
    command = sanitize_command(command)
    if not command:
        print("❌ Skipping interactive/unsafe command")
        return
    try:
        global wsl_current_dir
        cwd = os.getcwd()
        if wsl_current_dir is None:
            wsl_current_dir = _get_initial_wsl_cwd()
        wsl_cwd = wsl_current_dir
        user = os.getenv("VOICE_SHELL_WSL_USER", "").strip()
        distro = os.getenv("VOICE_SHELL_WSL_DISTRO", "").strip()
        args = ["wsl"]
        if distro:
            args += ["--distribution", distro]
        if user:
            args += ["--user", user]
        args += [
            "--cd", wsl_cwd,
            "--",
            "bash", "-lc", command,
        ]
        who = user or "<default>"
        which = distro or "<default>"
        print(f"💻 Executing in WSL: {command} (in {cwd}) [user={who}, distro={which}]")
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if stdout:
            print("🪄 Output:\n", stdout)
        else:
            print("🪄 Output:\n <no output>")
        if stderr:
            print("⚠️ Errors:\n", stderr)
        if result.returncode == 0:
            speak("Command executed successfully.")
            # Persist directory change for 'cd <path>' commands
            m = re.match(r"^\s*cd\s+(.+?)\s*$", command)
            if m:
                target = m.group(1)
                user_opts = []
                if distro:
                    user_opts += ["--distribution", distro]
                if user:
                    user_opts += ["--user", user]
                new_dir = _resolve_wsl_dir(wsl_cwd, target, user_opts)
                if new_dir != wsl_cwd:
                    wsl_current_dir = new_dir
                    print(f"📂 WSL CWD updated to: {wsl_current_dir}")
        else:
            print(f"❌ Command failed with exit code {result.returncode}")
            speak("Command failed.")
    except subprocess.TimeoutExpired:
        print("❌ Command timed out!")
        speak("Command timed out.")
    except FileNotFoundError as e:
        print("❌ 'wsl' not found. Ensure WSL is installed and available in PATH.")
        speak("WSL not found.")
    except Exception as e:
        print("❌ Error executing command:", e)
        speak("Error executing the command.")

def main_loop():
    speak("Voice shell started. Say your command.")
    while True:
        try:
            record_voice()
            text = transcribe_audio()
            if not text:
                continue

            normalized_text = tamil_to_tunglish(text)
            shell_cmd, exit_flag = get_command_and_exit(normalized_text)
            
            if shell_cmd in ["", "true", "ok"]:
                print("❌ No valid shell command generated, skipping.")
                continue
            if exit_flag:
                speak("Okay, exiting. Goodbye!")
                print("👋 Exit intent detected. Shutting down.")
                break

            execute_in_wsl(shell_cmd)
        except Exception as e:
            print("❌ Error in main loop:", e)
            speak("Something went wrong, please try again.")


# ---------------- Run ----------------
if __name__ == "__main__":
    try:
        tui_script = os.path.join(os.path.dirname(__file__), "terminal_gui.py")
        if os.path.exists(tui_script):
            # Launch the Rich TUI in a new console window on Windows so it pops up separately
            cmd = [sys.executable, tui_script]
            creation_flags = 0
            if os.name == 'nt':
                try:
                    creation_flags = subprocess.CREATE_NEW_CONSOLE
                except AttributeError:
                    creation_flags = 0
            try:
                subprocess.Popen(cmd, creationflags=creation_flags)
                # Exit the parent so only the popup TUI remains
                raise SystemExit(0)
            except Exception:
                # If popup launch fails, run in the same console
                subprocess.run(cmd, check=False)
        else:
            main_loop()
    except Exception:
        # Fallback to original CLI loop
        main_loop()
