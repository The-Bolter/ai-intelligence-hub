"""Independent refresh worker. Run under runtime_supervisor.py."""
import threading
import time

from app import _auto_refresh_loop
from runtime_health import write_scheduler_health


if __name__ == "__main__":
    refresh_thread = threading.Thread(target=_auto_refresh_loop, daemon=True)
    refresh_thread.start()
    while True:
        write_scheduler_health("running" if refresh_thread.is_alive() else "failed")
        time.sleep(30)
