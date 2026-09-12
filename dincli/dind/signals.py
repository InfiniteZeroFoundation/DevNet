"""Signal handlers for graceful daemon shutdown.

Installs SIGTERM/SIGINT handlers that set a threading.Event. Must be called
from the main thread (signal.signal restriction).
"""

import logging
import signal
from threading import Event

logger = logging.getLogger("dincli")


def install_shutdown_handlers(stop_event: Event) -> None:
    def _handler(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, initiating graceful shutdown", sig_name)
        stop_event.set()

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
