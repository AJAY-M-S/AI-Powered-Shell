# AI-Powered Voice Shell (Multilingual)

Voice-driven assistant that turns natural speech (Tamil/English/etc.) into safe Linux commands and executes them inside WSL on Windows. Uses Sarvam AI for Speech-to-Text (default), Google Gemini for normalization and command generation, and pyttsx3 for spoken feedback.

## Features
- Voice capture with simple VAD (records until you pause)
- Multilingual STT via Sarvam AI SDK (configurable language/model)
- Optional Whisper transcription provider
- Gemini translates/normalizes and outputs a single non-interactive Linux command
- Safety guardrails (blocks editors/pagers and risky interactive patterns)
- Executes in WSL with persistent working directory across `cd`
- Spoken status and console logs

## Architecture Overview
1. Record mic audio → `input.wav`
2. Transcribe (Sarvam AI or Whisper)
3. Gemini: normalize to clear English → return `{ command, exit }` JSON
4. Sanitize command (deny interactive tools, redirect patterns)
5. Execute in WSL with timeout and persist CWD on `cd`
6. Print stdout/stderr and speak result

Key files:
- `voice_shell_tunglish.py` (main app)
- `whisper_test.py` (standalone 5s record + Whisper transcribe demo)
- `.env` (provider/model/language keys; loaded via python-dotenv)
- `requirements.txt` (dependencies)
- `generate_report.py` (creates `Project_Report.docx`)

## Requirements
- Windows 10/11 with WSL installed (`wsl` available in PATH)
- Python 3.10+
- Microphone access

Python packages (see `requirements.txt`):
- `sarvamai`, `google-generativeai`, `python-dotenv`, `sounddevice`, `wavio`, `pyttsx3`, `numpy`
- Optional: `faster-whisper`, `torch`, `openai-whisper`
- Utilities: `requests`, `python-docx` (for report generation)

## Setup
1. Create and activate a virtual environment
   - PowerShell:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
2. Install dependencies
   ```powershell
   pip install -r requirements.txt
   ```
3. Configure environment (.env)
   - Copy/edit `.env` (already present) and set values:
     ```env
     # Sarvam AI Speech-to-Text
     SARVAM_API_KEY=YOUR_SARVAM_API_KEY
     SARVAM_STT_MODEL=saarika:v2.5
     SARVAM_LANGUAGE_CODE=ta-IN   # or en-IN, gu-IN, hi-IN, etc.

     # Provider selection
     TRANSCRIBE_PROVIDER=sarvam   # or whisper

     # Optional: WSL targeting
     # VOICE_SHELL_WSL_DISTRO=Ubuntu-22.04
     # VOICE_SHELL_WSL_USER=yourlinuxuser
     ```
   - Gemini API key is configured in code; consider reading it from env if you prefer.

## Running the App
```powershell
.\.venv\Scripts\Activate.ps1
python voice_shell_tunglish.py
```
- Speak your command when prompted. Recording stops after a short pause.
- The console shows the generated command and its outputs.
- The app speaks success/failure.
- Say “exit” to terminate.

## Example Interactions
- “List files here” → `ls -la`
- “Sample folder create pannu” → `mkdir Sample`
- “Open sample.py file” → `cat sample.py`
- “Change directory to Sample” → `cd Sample`
- “First twenty lines of sample.txt” → `head -n 20 sample.txt`

## WSL Behavior
- Commands run in your default WSL distro/user unless overridden by env:
  - `VOICE_SHELL_WSL_DISTRO`, `VOICE_SHELL_WSL_USER`
- Initial WSL CWD maps to your Windows project folder: `/mnt/c/.../AI-Powered-Shell`
- `cd` commands update the internal WSL CWD for subsequent runs.
- View Linux-only paths from Windows via `\\wsl$\<DistroName>\...`

## Safety Guardrails
- Blocks interactive tools: `nano`, `vi`, `vim`, `emacs`, `ed`, `less`, `more`, `man`, `top`, `htop`, `watch`, `code`, `notepad`
- Blocks `cat > file` and similar interactive redirections
- Per-command timeout (default 10s)

## Multilingual Support
- Controlled by `SARVAM_LANGUAGE_CODE` (e.g., `ta-IN`, `en-IN`, `gu-IN`)
- If recognition quality is poor, try adjusting the language code or model
- You can switch providers by setting `TRANSCRIBE_PROVIDER=whisper`

## Troubleshooting
- “No module named X”: Ensure venv is active and run `pip install -r requirements.txt`.
- “wsl not found”: Install/enable WSL and ensure `wsl` is on PATH.
- Mic not recording: Check Windows microphone permissions and device selection.
- Tamil accuracy issues: Set `SARVAM_LANGUAGE_CODE=ta-IN`; reduce background noise; speak clearly; consider VAD tweaks.
- Gemini output odd commands: Rephrase the instruction; we can tighten the prompt further if needed.
- Long-running commands: The app is designed for quick, non-interactive tasks; increase timeout if necessary.

## Optional Scripts
- Generate Word report:
  ```powershell
  python generate_report.py
  ```
  Produces `Project_Report.docx`.

- Whisper test (standalone):
  ```powershell
  python whisper_test.py
  ```
  Records 5s audio → transcribes with openai-whisper → prints text.

## Known Limitations
- Interactive programs are intentionally disallowed
- STT and LLM outputs can vary with audio/noise/context
- Requires WSL for command execution; not a native Windows shell controller

## Roadmap Ideas
- Command confirmation for sensitive actions
- Better Tamil prompt tuning and domain vocabulary
- History, undo helpers, and safer `rm` patterns
- Multi-step tasks with approvals

## Project Structure
```
AI-Powered-Shell/
├─ voice_shell_tunglish.py      # Main application
├─ whisper_test.py              # STT demo (5s record + Whisper)
├─ generate_report.py           # Exports Project_Report.docx
├─ requirements.txt             # Python dependencies
├─ .env                         # Runtime config (loaded by python-dotenv)
├─ *.txt / Sample/ ...          # Example files created during use
└─ .venv/                       # Virtual environment (local)
```

## License
Add your preferred license (e.g., MIT) as `LICENSE`.

## Acknowledgements
- Sarvam AI SDK (`sarvamai`) for Speech-to-Text
- Google Gemini (`google-generativeai`) for normalization and command generation
- WSL for Linux execution on Windows
- `sounddevice`, `wavio`, `pyttsx3` for audio I/O and TTS
