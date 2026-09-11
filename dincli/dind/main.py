"""dind Typer app — start | stop | status | preferences | capabilities.

All commands accept --state-dir so lifecycle ops can't target the wrong daemon.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import typer

from dincli import __version__
from dincli.dind import control
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
from dincli.dind.process import read_pid, remove_pid, write_pid

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

        # Stale-artifact cleanup, running behind the lock: holding it
        # exclusively already proves no other dind owns this state dir, so
        # any leftover PID file or control descriptor here is a crash
        # remnant — whether or not that old PID happens to still be alive
        # (it may have been reused by an unrelated process). Rejecting
        # startup on PID liveness alone, even after acquiring the lock, was
        # review finding 4's second defect: the lock is authoritative, a
        # reused PID is not evidence of anything.
        if read_pid(paths.pid_path) is not None:
            remove_pid(paths.pid_path)
        control.remove_descriptor(paths.control_path)

        # Test-only: widens the check→write window so a race test can
        # deterministically force two `dind start` invocations to overlap
        # inside it, rather than relying on interpreter-startup jitter to
        # happen to line them up. Inert in normal operation — the env var is
        # never set outside tests. Placed behind the lock deliberately: the
        # lock (or its absence, in a test that neuters it) is exactly what
        # this sleep is meant to help distinguish.
        _test_delay_s = os.environ.get("DIN_DIND_TEST_PID_DELAY_S")
        if _test_delay_s:
            time.sleep(float(_test_delay_s))

        write_pid(paths.pid_path)
        wrote_pid = True

        stop_event = threading.Event()
        install_shutdown_handlers(stop_event)

        # Local control channel (review finding 4): lets `stop`/`status`
        # verify they're talking to THIS instance instead of trusting a
        # bare, reusable PID. A control-triggered stop sets the same
        # stop_event a SIGTERM would, so it takes the identical shutdown
        # path. Deliberately non-fatal to the daemon's own startup if it
        # can't be established (e.g. no usable control directory) — the
        # daemon still runs, but `stop`/`status` will report the lock-held/
        # control-unavailable state and refuse to guess rather than
        # fall back to signalling a PID (see control.py, main.py::stop()).
        control_server = None
        instance_id = control.new_instance_id()
        try:
            control_socket_path = control.socket_path_for(paths.state_dir)
            control_server = control.ControlServer(control_socket_path, instance_id, stop_event)
            control_server.start()
            control.write_descriptor(
                paths.control_path,
                control.ControlDescriptor(
                    instance_id=instance_id,
                    socket_path=str(control_socket_path),
                    pid=os.getpid(),
                ),
            )
        except control.ControlError as e:
            logger.warning(
                "dind control endpoint unavailable (%s) — `dind stop` will "
                "require a process supervisor for this run.", e,
            )
            control_server = None

        state = StateStore(paths.db_path)
        # Schema migration first, once, before the health thread opens its
        # own per-thread connection — see StateStore.initialize().
        state.initialize()
        state.set_meta("started_at", datetime.now(timezone.utc).isoformat())
        state.reset_running_jobs()

        health = HealthServer(host, port, state)
        health_thread = threading.Thread(target=health.run, daemon=True)
        health_thread.start()

        control_thread = None
        if control_server is not None:
            control_thread = threading.Thread(target=control_server.run, daemon=True)
            control_thread.start()

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

            if control_server is not None:
                control_server.shutdown()
                if control_thread is not None:
                    control_thread.join(timeout=5)
            control.remove_descriptor(paths.control_path)

            health.shutdown()
            health_thread.join(timeout=5)

            state.close()

            logger.info("dind daemon shut down")
    finally:
        # wrote_pid guards against deleting artifacts this invocation never
        # wrote (e.g. the "already running" branch above, raised while still
        # holding the lock).
        if wrote_pid:
            remove_pid(paths.pid_path)
            control.remove_descriptor(paths.control_path)
        release_state_lock(lock_fd)


@app.command()
def stop(
    state_dir: str | None = STATE_DIR,
    timeout: int = typer.Option(
        30, "--timeout", "-t",
        help="Seconds to wait for the daemon to stop.",
    ),
) -> None:
    """Stop a running dind daemon through its verified control channel.

    Review finding 4: a PID read from disk, re-checked a moment later
    against "is the lock held", does not prove that PID still names the
    process holding the lock — a replacement daemon can start in between,
    or the PID can simply be reused by an unrelated process. This command
    never signals a PID directly. Instead it asks, over a same-user local
    control channel, whichever process currently holds the state
    directory's exclusive lock to shut itself down, and validates that the
    process on the other end is still the specific instance the descriptor
    named (see dincli/dind/control.py for exactly what that does and does
    not guarantee). If that channel is unavailable — no descriptor, an
    older daemon, an unresponsive endpoint — this reports the condition and
    refuses to guess; stop it through your process supervisor instead.
    """
    resolved = resolve_state_dir(state_dir)
    paths = StateDirs(resolved)

    pid = read_pid(paths.pid_path)
    if pid is None:
        typer.echo(
            f"No PID file found at {paths.pid_path}. Is dind running?",
            err=True,
        )
        raise typer.Exit(1)

    # Try to take the lock ourselves rather than merely probing it: if we
    # succeed, that proves — atomically, under the same lock that makes
    # `start()` exclusive — that nobody owns this state dir right now, so
    # any PID/control artifacts left here are stale. Cleaning them up while
    # still holding the lock (instead of probing, releasing, then deleting)
    # closes the race where a concurrent `start()` could begin between the
    # probe and the delete.
    lock_fd = acquire_state_lock(paths.lock_path)
    if lock_fd is not None:
        try:
            typer.echo(f"PID {pid} is stale — cleaning up.")
            remove_pid(paths.pid_path)
            control.remove_descriptor(paths.control_path)
        finally:
            release_state_lock(lock_fd)
        return

    # Someone holds the lock right now. Read the descriptor as late as
    # possible — immediately before connecting — to narrow (not eliminate)
    # the window in which a replacement instance could take over. The
    # server-side instance-id check closes the remainder: if a replacement
    # starts between this read and the connection below, it holds a
    # different id and rejects the request instead of silently acting on
    # behalf of whatever now holds the lock.
    descriptor = control.read_descriptor(paths.control_path)
    if descriptor is None:
        typer.echo(
            f"dind's lock is held (PID {pid}) but no control endpoint is "
            "recorded for it — an older daemon, one still starting, or a "
            "corrupt/missing descriptor. Refusing to signal that PID "
            "directly; stop it through your process supervisor instead.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        response = control.send_command(descriptor.socket_path, descriptor.instance_id, "stop")
    except control.ControlError as e:
        typer.echo(
            f"dind's lock is held (PID {pid}) but its control endpoint did "
            f"not respond ({e}). Refusing to signal that PID directly; "
            "stop it through your process supervisor instead.",
            err=True,
        )
        raise typer.Exit(1)

    if response.get("status") != "ok":
        reason = response.get("reason", "unknown")
        if reason == "instance_mismatch":
            typer.echo(
                "A different dind instance now holds this state directory "
                "(it replaced the one this stop targeted, between the "
                "descriptor being read and this request). Not signalling "
                "it — re-run `dind stop` to target the current instance.",
                err=True,
            )
        else:
            typer.echo(f"dind rejected the stop request: {reason}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Stop acknowledged by PID {descriptor.pid}. Waiting up to {timeout}s...")
    for _ in range(timeout):
        if not is_locked(paths.lock_path):
            typer.echo("dind stopped.")
            return
        time.sleep(1)

    typer.echo(f"dind did not stop within {timeout}s.", err=True)
    raise typer.Exit(1)


@app.command()
def status(
    state_dir: str | None = STATE_DIR,
) -> None:
    """Check whether a dind daemon is running (PID + optional /health).

    Distinguishes stopped, lock-held-but-unverified, and verified-running:
    holding the state-directory lock proves *some* process owns this state
    dir, but not that it is the specific instance named by the PID file —
    only a successful round trip on the control channel proves that (review
    finding 4). This command is read-only: unlike `stop`, it never attempts
    to acquire the lock or clean up stale artifacts itself.
    """
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

    descriptor = control.read_descriptor(paths.control_path)
    verified = False
    if descriptor is not None:
        try:
            response = control.send_command(
                descriptor.socket_path, descriptor.instance_id, "ping", timeout=2.0
            )
            verified = response.get("status") == "ok"
        except control.ControlError:
            verified = False

    if not verified:
        typer.echo(
            f"dind's lock is held (PID {pid}) but its control endpoint "
            "could not be verified — treat this as \"probably running\", "
            "not confirmed. An older daemon, one still starting, or an "
            "unresponsive process can all look like this."
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
