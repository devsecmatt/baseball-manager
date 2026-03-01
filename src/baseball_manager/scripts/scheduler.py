"""
Scheduler daemon for daily baseball manager tasks.

Runs bbm report each morning at a configured time.
Used as the entry point for the launchd agent.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import schedule

LOG_DIR = Path(__file__).parent.parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "scheduler.log"

BBM = Path(__file__).parent.parent.parent.parent / ".venv" / "bin" / "bbm"


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_daily_report() -> None:
    logging.info("=== Running daily report ===")
    report_log = LOG_DIR / f"report_{datetime.now().strftime('%Y-%m-%d')}.log"
    try:
        result = subprocess.run(
            [str(BBM), "report"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        report_log.write_text(output)
        logging.info(f"Report complete. Output saved to {report_log.name}")
        if result.returncode != 0:
            logging.warning(f"Report exited with code {result.returncode}")
    except subprocess.TimeoutExpired:
        logging.error("Report timed out after 120s")
    except Exception as e:
        logging.error(f"Report failed: {e}")


def run_daemon(run_time: str = "08:00") -> None:
    """Run the scheduler daemon indefinitely."""
    _setup_logging()
    logging.info(f"Baseball Manager scheduler started. Daily report at {run_time}.")

    schedule.every().day.at(run_time).do(run_daily_report)

    # Run immediately on start if it's past the scheduled time today
    now = datetime.now().strftime("%H:%M")
    if now >= run_time:
        logging.info("Past scheduled time for today — running report now.")
        run_daily_report()

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    run_time = sys.argv[1] if len(sys.argv) > 1 else "08:00"
    run_daemon(run_time)
