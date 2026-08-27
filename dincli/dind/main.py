"""dind Typer app — start | stop | status | preferences | capabilities.

All commands accept --state-dir so lifecycle ops can't target the wrong daemon.
"""

import json
import signal
import threading
import time
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import typer

from dincli import __version__
from dincli.dind.config import (
    resolve_health_host,
    resolve_health_port,
    resolve_state_dir,
    validate_health_port,
)
from dincli.dind.paths import StateDirs
from dincli.dind.preferences import (
    Preferences,
    VALID_RISK_TOLERANCES,
    load_preferences,
    save_preferences,
)
from dincli.dind.process import (
    is_process_running,
    read_pid,
    remove_pid,
    send_signal,
    write_pid,
)

app = typer.Typer(
    help=f"DIN Daemon (dind) v{__version__} — always-on process framework.",
    pretty_exceptions_enable=False,
)

_STATE_DIR_HELP = "Path to dind state directory (pid, db). Env: DIN_DIND_STATE_DIR. Default: XDG_CACHE/dincli/dind"

STATE_DIR = typer.Option(
    None, "--state-dir", help=_STATE_DIR_HELP,
)


@app.command()
def start(
    state_dir: str | None = STATE_DIR,
    health_host: str | None = typer.Option(
        None,
        "--health-host",
        help="Health bind host. Env: DIN_DIND_HEALTH_HOST. Default: 127.0.0.1",
    ),
    health_port: int | None = typer.Option(
        None,
        "--health-port",
        help="Health bind port. Env: DIN_DIND_HEALTH_PORT. Default: 8787",
    ),
) -> None:
    """Start the dind daemon (foreground)."""
    resolved = resolve_state_dir(state_dir)
    paths = StateDirs(resolved)

    existing_pid = read_pid(paths.pid_path)
    if existing_pid is not None and is_process_running(existing_pid):
        typer.echo(
            f"dind already running (PID {existing_pid}) in {resolved}",
            err=True,
        )
        raise typer.Exit(1)

    if existing_pid is not None:
        remove_pid(paths.pid_path)

    host = resolve_health_host(health_host)
    port = resolve_health_port(health_port)
    validate_health_port(port)

    from dincli.dind.daemon import DaemonLoop
    from dincli.dind.health import HealthServer
    from dincli.dind.logging import configure_logging
    from dincli.dind.signals import install_shutdown_handlers
    from dincli.dind.state import StateStore

    configure_logging("json")

    import logging
    logger = logging.getLogger("dincli")

    write_pid(paths.pid_path)

    stop_event = threading.Event()
    install_shutdown_handlers(stop_event)

    state = StateStore(paths.db_path)
    state.set_meta("started_at", datetime.now(timezone.utc).isoformat())
    state.reset_running_jobs()

    health = HealthServer(host, port, state)
    health_thread = threading.Thread(target=health.run, daemon=True)
    health_thread.start()

    loop = DaemonLoop(state, stop_event)
    try:
        logger.info("dind daemon started (state=%s)", resolved)
        loop.run()
    finally:
        logger.info("Shutting down dind daemon...")

        state.reset_running_jobs()
        shutdown_count_str = state.get_meta("shutdown_count") or "0"
        state.set_meta("shutdown_count", str(int(shutdown_count_str) + 1))

        health.shutdown()
        health_thread.join(timeout=5)

        remove_pid(paths.pid_path)
        state.close()

        logger.info("dind daemon shut down")


@app.command()
def stop(
    state_dir: str | None = STATE_DIR,
    timeout: int = typer.Option(
        30, "--timeout", "-t",
        help="Seconds to wait for the daemon to stop after SIGTERM.",
    ),
) -> None:
    """Stop a running dind daemon via its PID file."""
    resolved = resolve_state_dir(state_dir)
    paths = StateDirs(resolved)

    pid = read_pid(paths.pid_path)
    if pid is None:
        typer.echo(
            f"No PID file found at {paths.pid_path}. Is dind running?",
            err=True,
        )
        raise typer.Exit(1)

    if not is_process_running(pid):
        typer.echo(f"PID {pid} is stale — cleaning up.")
        remove_pid(paths.pid_path)
        return

    send_signal(pid, signal.SIGTERM)
    typer.echo(f"Sent SIGTERM to PID {pid}. Waiting up to {timeout}s...")

    for _ in range(timeout):
        if not is_process_running(pid):
            typer.echo("dind stopped.")
            return
        time.sleep(1)

    typer.echo(f"dind did not stop within {timeout}s.", err=True)
    raise typer.Exit(1)


@app.command()
def status(
    state_dir: str | None = STATE_DIR,
) -> None:
    """Check whether a dind daemon is running (PID + optional /health)."""
    resolved = resolve_state_dir(state_dir)
    paths = StateDirs(resolved)

    pid = read_pid(paths.pid_path)
    if pid is None:
        typer.echo("dind is not running (no PID file).")
        return

    running = is_process_running(pid)
    if not running:
        typer.echo(
            f"dind is stopped (stale PID {pid} in {paths.pid_path})."
        )
        return

    typer.echo(f"dind is running  PID {pid}  state-dir {resolved}")

    try:
        from dincli.dind.state import StateStore

        store = StateStore(paths.db_path)
        health_host = store.get_meta("health_host") or resolve_health_host()
        health_port_str = store.get_meta("health_port")
        health_port = (
            int(health_port_str)
            if health_port_str
            else resolve_health_port()
        )

        url = f"http://{health_host}:{health_port}/health"
        with urllib.request.urlopen(url, timeout=5) as resp:
            health = json.loads(resp.read())

        typer.echo(f"  Health:    {health['status']}")
        typer.echo(f"  Uptime:    {health['uptime_s']}s")
        typer.echo(
            f"  Pending:   {health['queue']['pending']}  "
            f"Running: {health['queue']['running']}  "
            f"Failed: {health['queue']['failed']}"
        )
        typer.echo(
            f"  CPU count: {health['resources']['cpu_count']}"
        )
    except Exception:
        typer.echo("  (health endpoint unavailable)")


preferences_app = typer.Typer(help="Local daemon preferences.")
app.add_typer(preferences_app, name="preferences")


PREFS_STATE_DIR = typer.Option(
    None, "--state-dir", help=_STATE_DIR_HELP,
)


@preferences_app.command("show")
def preferences_show(state_dir: str | None = PREFS_STATE_DIR) -> None:
    resolved = resolve_state_dir(state_dir)
    paths = StateDirs(resolved)
    prefs = load_preferences(paths.preferences_path)
    typer.echo(json.dumps(asdict(prefs), indent=2))


@preferences_app.command("set")
def preferences_set(
    state_dir: str | None = PREFS_STATE_DIR,
    domain: str | None = typer.Option(None, "--domain"),
    risk_tolerance: str | None = typer.Option(None, "--risk-tolerance"),
    min_reward: int | None = typer.Option(None, "--min-reward"),
    privacy: list[str] | None = typer.Option(None, "--privacy"),
) -> None:
    resolved = resolve_state_dir(state_dir)
    paths = StateDirs(resolved)
    prefs = load_preferences(paths.preferences_path)

    if risk_tolerance is not None and risk_tolerance not in VALID_RISK_TOLERANCES:
        raise typer.BadParameter(
            f"Must be one of: {', '.join(sorted(VALID_RISK_TOLERANCES))}"
        )

    if domain is not None:
        prefs.domain = domain
    if risk_tolerance is not None:
        prefs.risk_tolerance = risk_tolerance
    if min_reward is not None:
        prefs.min_expected_reward = min_reward
    if privacy is not None:
        prefs.privacy_constraints = privacy

    save_preferences(paths.preferences_path, prefs)
    typer.echo(json.dumps(asdict(prefs), indent=2))


@app.command()
def capabilities(state_dir: str | None = STATE_DIR) -> None:
    from dincli.dind.capabilities import detect_capabilities

    resolved = resolve_state_dir(state_dir)
    summary = detect_capabilities(resolved)
    typer.echo(json.dumps(asdict(summary), indent=2))
