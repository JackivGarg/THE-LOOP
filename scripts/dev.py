"""Start the API and React development server with one command, on Windows/Linux."""
import shutil
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("Node.js/npm are required. Install Node.js 22+ and run npm ci in frontend first.")
    if not (ROOT / "frontend" / "node_modules").exists():
        raise SystemExit("Install frontend dependencies first: cd frontend && npm ci")
    processes = []
    launch_options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    try:
        processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, **launch_options))
        processes.append(subprocess.Popen([npm, "run", "dev", "--", "--port", "5180", "--strictPort"], cwd=ROOT / "frontend", **launch_options))
        print("\nTHE LOOP: http://127.0.0.1:5180 | API docs: http://127.0.0.1:8000/docs\n", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        failed = next((process.returncode for process in processes if process.returncode), 0)
        if failed:
            raise SystemExit(failed)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == "nt":
                    # npm launches a child Node process; stop only this launcher's tree.
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                else:
                    os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
