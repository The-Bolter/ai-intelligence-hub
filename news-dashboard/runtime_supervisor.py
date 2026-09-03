"""Windows-friendly local supervisor for independent Web and scheduler processes."""
from __future__ import annotations

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
CHILDREN = ("web_server.py", "scheduler_worker.py")


def start(script):
    return subprocess.Popen([sys.executable, script], cwd=ROOT)


def main():
    processes = {script: start(script) for script in CHILDREN}
    while True:
        for script, process in tuple(processes.items()):
            if process.poll() is not None:
                processes[script] = start(script)
        time.sleep(3)


if __name__ == "__main__":
    main()
