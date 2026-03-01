"""
macOS launchd plist generator and installer for the daily scheduler.

Installs to ~/Library/LaunchAgents/com.baseball-manager.daily.plist
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLIST_LABEL = "com.baseball-manager.daily"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
SCHEDULER = PROJECT_ROOT / "src" / "baseball_manager" / "scripts" / "scheduler.py"
LOG_DIR = PROJECT_ROOT / "logs"


def _build_plist(hour: int, minute: int) -> str:
    log_out = LOG_DIR / "launchd_stdout.log"
    log_err = LOG_DIR / "launchd_stderr.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{PYTHON}</string>
        <string>{SCHEDULER}</string>
        <string>{hour:02d}:{minute:02d}</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>{log_out}</string>

    <key>StandardErrorPath</key>
    <string>{log_err}</string>

    <key>WorkingDirectory</key>
    <string>{PROJECT_ROOT}</string>

    <key>RunAtLoad</key>
    <false/>

    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""


def install(run_time: str = "08:00") -> None:
    hour, minute = map(int, run_time.split(":"))
    LOG_DIR.mkdir(exist_ok=True)
    plist_content = _build_plist(hour, minute)

    PLIST_PATH.write_text(plist_content)
    print(f"Plist written to {PLIST_PATH}")

    # Unload if already loaded, then reload
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)],
                   capture_output=True)
    result = subprocess.run(["launchctl", "load", str(PLIST_PATH)],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Scheduler installed. Daily report will run at {run_time}.")
        print(f"Logs: {LOG_DIR}/")
    else:
        print(f"launchctl load failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)


def uninstall() -> None:
    if not PLIST_PATH.exists():
        print("Scheduler not installed.")
        return
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    PLIST_PATH.unlink()
    print("Scheduler uninstalled.")


def status() -> None:
    result = subprocess.run(
        ["launchctl", "list", PLIST_LABEL],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"Scheduler is LOADED:\n{result.stdout}")
    else:
        print("Scheduler is NOT loaded.")

    log_out = LOG_DIR / "launchd_stdout.log"
    if log_out.exists():
        lines = log_out.read_text().splitlines()
        recent = lines[-30:] if len(lines) > 30 else lines
        print("\n--- Recent output ---")
        print("\n".join(recent))
