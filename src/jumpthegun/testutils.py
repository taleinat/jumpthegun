import signal
import sys
import time


def sleep_and_exit_on_signal():
    def signal_handler(signum, frame):
        print(f"Received signal: {signum}", flush=True)
        sys.exit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGUSR1, signal_handler)
    signal.signal(signal.SIGUSR2, signal_handler)

    print("Sleeping...", flush=True)
    time.sleep(60.0)
    print("Done.", flush=True)
