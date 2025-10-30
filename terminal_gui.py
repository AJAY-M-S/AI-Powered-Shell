import os
import re
import shlex
import subprocess
from datetime import datetime

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Reuse core pipeline pieces from the existing app
import voice_shell_tunglish as core

console = Console()


def exec_in_wsl_capture(command: str, timeout: int = 10):
    """Execute a sanitized, non-interactive command in WSL and return result fields.
    Returns dict: {returncode, stdout, stderr, updated_cwd or None}
    """
    if not command:
        return {"returncode": None, "stdout": "", "stderr": "", "updated_cwd": None}

    command = core.sanitize_command(command)
    if not command:
        return {"returncode": None, "stdout": "", "stderr": "Unsafe/interactive command blocked.", "updated_cwd": None}

    try:
        # Track current WSL cwd similar to the original function
        if core.wsl_current_dir is None:
            core.wsl_current_dir = core._get_initial_wsl_cwd()
        wsl_cwd = core.wsl_current_dir

        user = os.getenv("VOICE_SHELL_WSL_USER", "").strip()
        distro = os.getenv("VOICE_SHELL_WSL_DISTRO", "").strip()

        args = ["wsl"]
        if distro:
            args += ["--distribution", distro]
        if user:
            args += ["--user", user]
        args += ["--cd", wsl_cwd, "--", "bash", "-lc", command]

        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        updated_cwd = None
        if result.returncode == 0:
            # Persist directory change for 'cd <path>' commands
            m = re.match(r"^\s*cd\s+(.+?)\s*$", command)
            if m:
                target = m.group(1)
                user_opts = []
                if distro:
                    user_opts += ["--distribution", distro]
                if user:
                    user_opts += ["--user", user]
                new_dir = core._resolve_wsl_dir(wsl_cwd, target, user_opts)
                if new_dir != wsl_cwd:
                    core.wsl_current_dir = new_dir
                    updated_cwd = new_dir

        return {
            "returncode": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "updated_cwd": updated_cwd,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": None, "stdout": "", "stderr": "Command timed out.", "updated_cwd": None}
    except FileNotFoundError:
        return {"returncode": None, "stdout": "", "stderr": "'wsl' not found. Ensure WSL is installed and on PATH.", "updated_cwd": None}
    except Exception as e:
        return {"returncode": None, "stdout": "", "stderr": f"Error executing command: {e}", "updated_cwd": None}


def build_layout(status: str, transcript: str, command: str, output: str, errors: str):
    from rich.layout import Layout

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3),
    )

    header_text = Text.from_markup(
        f"[bold cyan]AI-Powered Voice Shell[/]  |  [white]Status:[/] [bold]{status}[/]  |  {datetime.now().strftime('%H:%M:%S')}"
    )
    layout["header"].update(Panel(header_text, border_style="cyan"))

    body = Layout()
    body.split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    left_table = Table.grid(padding=(0, 1))
    left_table.add_row("[bold]Transcript[/]")
    left_table.add_row(transcript or "<waiting>")
    left_table.add_row("")
    left_table.add_row("[bold]Command[/]")
    left_table.add_row(command or "-")

    right_table = Table.grid(padding=(0, 1))
    right_table.add_row("[bold]Output[/]")
    right_table.add_row(output or "<no output>")
    if errors:
        right_table.add_row("")
        right_table.add_row("[bold red]Errors[/]")
        right_table.add_row(f"[red]{errors}[/]")

    body["left"].update(Panel(left_table, title="Request", border_style="magenta"))
    body["right"].update(Panel(right_table, title="Response", border_style="green"))

    layout["body"].update(body)

    listen_hint = "Speak now" if status.lower().startswith("listening") else "Processing..."
    footer_text = Text.from_markup(
        f"[bold]{listen_hint}[/]  |  Press Ctrl+C to quit. Say 'exit' to end the session."
    )
    layout["footer"].update(Panel(footer_text, border_style="cyan"))

    return layout


def run_tui_loop():
    transcript = ""
    command = ""
    output = ""
    errors = ""

    core.speak("Voice shell started. Say your command.")
    status = "Listening – Speak now"

    with Live(build_layout(status, transcript, command, output, errors), refresh_per_second=8, console=console) as live:
        while True:
            try:
                status = "Listening – Speak now"
                live.update(build_layout(status, transcript, command, output, errors))

                core.record_voice()

                status = "Transcribing"
                live.update(build_layout(status, transcript, command, output, errors))
                transcript = core.transcribe_audio() or ""

                if not transcript.strip():
                    continue

                status = "Thinking"
                live.update(build_layout(status, transcript, command, output, errors))
                normalized_text = core.tamil_to_tunglish(transcript)
                command, exit_flag = core.get_command_and_exit(normalized_text)

                if (command or "").strip() in ["", "true", "ok"]:
                    errors = "No valid shell command generated."
                    output = ""
                    continue

                if exit_flag:
                    status = "Exiting"
                    live.update(build_layout(status, transcript, command, output, errors))
                    core.speak("Okay, exiting. Goodbye!")
                    console.print(Panel("Exit intent detected. Shutting down.", border_style="red"))
                    break

                status = "Executing"
                live.update(build_layout(status, transcript, command, output, errors))
                res = exec_in_wsl_capture(command)
                output = res.get("stdout", "") or "<no output>"
                errors = res.get("stderr", "")
                rc = res.get("returncode")

                if rc == 0:
                    core.speak("Command executed successfully.")
                elif rc is None:
                    core.speak("Command failed.")
                else:
                    core.speak("Command failed.")

                status = "Listening – Speak now"
                live.update(build_layout(status, transcript, command, output, errors))

            except KeyboardInterrupt:
                core.speak("Goodbye!")
                console.print(Panel("Interrupted by user. Exiting.", border_style="red"))
                break
            except Exception as e:
                errors = f"Unexpected error: {e}"
                output = ""
                status = "Error"
                live.update(build_layout(status, transcript, command, output, errors))
                core.speak("Something went wrong, please try again.")


if __name__ == "__main__":
    run_tui_loop()
