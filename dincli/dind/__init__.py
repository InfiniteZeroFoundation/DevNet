"""DIN Daemon (dind) — always-on process framework (P4-1.1).

The daemon drives the protocol event loop, job queue, health endpoint, and
graceful shutdown. It imports from ``dincli.sdk`` (config, log, errors) never
from ``dincli.cli``.
"""

__version__ = "0.1.0"
