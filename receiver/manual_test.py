"""Open the existing bounded native trial in the user's normal Chrome."""
from pathlib import Path
import json
import queue
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DURATION = 150


def main():
    print("Keep the iPhone connected by USB, unlocked, with CarDash V2 visible.", flush=True)
    print("Starting a 150-second native CarPlay video/touch test. Audio is not implemented.", flush=True)
    child = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "receiver/run_trial.py"), str(DURATION)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )
    lines = queue.Queue()

    def relay():
        for line in child.stdout:
            lines.put(line)

    thread = threading.Thread(target=relay, daemon=True)
    thread.start()
    trial = None
    opened = False
    notice = False
    started = time.monotonic()
    try:
        while child.poll() is None or thread.is_alive() or not lines.empty():
            try:
                line = lines.get(timeout=0.2)
                print(line, end="", flush=True)
                if line.startswith("Trial "):
                    trial = Path(line[6:].strip())
            except queue.Empty:
                pass
            if trial and not opened and child.poll() is None:
                try:
                    token = (trial / "control-token.txt").read_text().strip()
                    request = urllib.request.Request(
                        "http://127.0.0.1:46205/status",
                        headers={"X-CarDash-Research-Token": token},
                    )
                    with urllib.request.urlopen(request, timeout=1) as response:
                        status = json.load(response)
                    if status.get("nativeFrames", 0) and status.get("videoConnected"):
                        subprocess.run(
                            ["/usr/bin/open", "-a", "Google Chrome",
                             "http://127.0.0.1:46205/#" + token], check=True,
                        )
                        opened = True
                        print("Chrome is open. Click native icons and the bottom-left Home button.", flush=True)
                        print("The test ends automatically; Ctrl+C stops it sooner.", flush=True)
                except (OSError, ValueError):
                    # The receiver may still be completing native authentication.
                    pass
            if not opened and not notice and time.monotonic() - started > 25:
                print("Still waiting for native video. Keep this window open for the diagnostic result.", flush=True)
                notice = True
        code = child.wait()
        if not opened:
            print("No viewer opened. The diagnostic output above identifies where to investigate.")
            return code or 1
        print("Test finished. Chrome may now say 'Native session ended'; that is expected.")
        print("Run this launcher again for another test. Logs are in the printed evidence directory.")
        return code
    except KeyboardInterrupt:
        print("\nStopping the research session and collecting cleanup…", flush=True)
        return 130
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=25)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    sys.exit(main())
