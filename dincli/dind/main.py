"""dind Typer app — start | stop | status | preferences | capabilities.

All commands accept --state-dir so lifecycle ops can't target the wrong daemon.
"""

import json
import signal
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import typer

from dincli import __version__
from dincli.dind.config import (
    resolve_health_host,
    resolve_health_port,
    resolve_max_ticks,
    resolve_state_dir,
    validate_health_port,
)
from dincli.dind.lock import acquire_state_lock, is_locked, release_state_lock
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

    # Atomic start (BL-19): the lock, not the PID file, is the source of
    # truth for "is a dind already running here". An flock is released by
    # the kernel on any process death, including SIGKILL, so — unlike an
    # O_EXCL marker — it can never itself go stale.
    lock_fd = acquire_state_lock(paths.lock_path)
    if lock_fd is None:
        existing_pid = read_pid(paths.pid_path)
        if existing_pid is not None:
            # Byte-identical to the pre-lock wording.
            typer.echo(
                f"dind already running (PID {existing_pid}) in {resolved}",
                err=True,
            )
        else:
            # The winner holds the lock but hasn't written its PID yet.
            typer.echo(f"dind already starting in {resolved}", err=True)
        raise typer.Exit(1)

    wrote_pid = False
    try:
        host = resolve_health_host(health_host)
        port = resolve_health_port(health_port)
        validate_health_port(port)
        max_ticks = resolve_max_ticks()

        from dincli.dind.daemon import DaemonLoop
        from dincli.dind.health import HealthServer
        from dincli.dind.logging import configure_logging
        from dincli.dind.signals import install_shutdown_handlers
        from dincli.dind.state import StateStore
        from dincli.sdk.session import DinSession

        configure_logging("json", state_dir=paths.state_dir)

        import logging
        logger = logging.getLogger("dincli")

        # Unchanged stale-PID cleanup, now running behind the lock: holding
        # the lock exclusively means any leftover PID file can only be a
        # crash remnant, never a live daemon on this state dir.
        existing_pid = read_pid(paths.pid_path)
        if existing_pid is not None and is_process_running(existing_pid):
            typer.echo(
                f"dind already running (PID {existing_pid}) in {resolved}",
                err=True,
            )
            raise typer.Exit(1)

        if existing_pid is not None:
            remove_pid(paths.pid_path)

        write_pid(paths.pid_path)
        wrote_pid = True

        stop_event = threading.Event()
        install_shutdown_handlers(stop_event)

        state = StateStore(paths.db_path)
        # Schema migration first, once, before the health thread opens its
        # own per-thread connection — see StateStore.initialize().
        state.initialize()
        state.set_meta("started_at", datetime.now(timezone.utc).isoformat())
        state.reset_running_jobs()

        health = HealthServer(host, port, state)
        health_thread = threading.Thread(target=health.run, daemon=True)
        health_thread.start()

        # A bare DinSession(): every property is lazy, so construction
        # touches neither the chain nor the keystore (§3.7). No new flags.
        loop = DaemonLoop(state, stop_event, max_ticks=max_ticks, session=DinSession())
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

            state.close()

            logger.info("dind daemon shut down")
    finally:
        # wrote_pid guards against deleting a PID file this invocation never
        # wrote (e.g. the "already running" branch above, raised while still
        # holding the lock).
        if wrote_pid:
            remove_pid(paths.pid_path)
        release_state_lock(lock_fd)


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

    if not is_locked(paths.lock_path):
        # A free lock is positive evidence no daemon owns this state dir,
        # regardless of what the PID file says — it may name a live but
        # unrelated process that happens to have reused the PID.
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

    if not is_locked(paths.lock_path):
        # See stop(): the lock, not the PID file, is authoritative.
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
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                health = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            # BL-20: a degraded daemon answers 503, which urlopen raises as
            # HTTPError before the body is read. The exception object is
            # itself a response — read the body off it instead of treating
            # this as "unreachable", which would make a degraded daemon look
            # worse than the bug this fixes. A non-HTTP failure or an
            # unparseable body still falls through to the except below.
            health = json.loads(e.read())

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
