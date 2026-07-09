# din-node — the trusted DIN host process, containerized.
#
# This image packages `dincli` (the trusted control plane that holds wallet /
# network config and decides what to submit on-chain) together with the Docker
# *client* binary, so that from inside this container `dincli` can shell out to
# `docker run` exactly like it does on a bare host today (see
# dincli/cli/worker.py). The worker containers it spawns run as SIBLINGS on the
# host Docker daemon via the mounted /var/run/docker.sock — NOT nested inside
# din-node. See dincli/docker/node/README.md (operator runbook) for the
# docker.sock trust tradeoff.
#
# Build (from repo root):
#   docker build -f dincli/docker/node/Dockerfile -t din-node:dev .
# Normally you build/run this via dincli/docker/node/docker-compose.yml.

FROM python:3.12-slim

# ---- Pins (surfaced as build args so an operator/CI can override) ----------
# dincli version is pinned implicitly by the source tree copied in below
# (pyproject.toml -> version = "0.1.0"). Python is pinned by the base tag above.
# DOCKER_CLI_VERSION: e.g. "5:27.3.1-1~debian.12~bookworm"; empty = latest in repo.
ARG DOCKER_CLI_VERSION=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ---- Docker CLI client (no daemon) -----------------------------------------
# Installed from Docker's official apt repo. We install ONLY docker-ce-cli:
# din-node talks to the *host* daemon over the mounted socket, so it needs the
# client binary but never its own daemon.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc; \
    chmod a+r /etc/apt/keyrings/docker.asc; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list; \
    apt-get update; \
    if [ -n "$DOCKER_CLI_VERSION" ]; then \
        apt-get install -y --no-install-recommends "docker-ce-cli=$DOCKER_CLI_VERSION"; \
    else \
        apt-get install -y --no-install-recommends docker-ce-cli; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
    docker --version

# ---- dincli (built install, pinned deps) -----------------------------------
WORKDIR /opt/dincli
# Copy only what the build needs, in cache-friendly order: pinned requirements
# first (rarely change) so the heavy dependency layer is reused across edits.
COPY dincli/requirements.txt ./dincli/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r dincli/requirements.txt

COPY pyproject.toml README.md MANIFEST.in ./
COPY dincli ./dincli
# Non-editable install: din-node is a release artifact; upgrades rebuild the
# image rather than mutating mounted source.
RUN python -m pip install --no-cache-dir . \
    && dincli version

# ---- Non-root user ---------------------------------------------------------
# Default uid/gid 1000 matches the typical first Linux user. The operator can
# override at runtime (compose `user:`) so files written into the bind-mounted
# state dir — and into worker output dirs, which workers create as din-node's
# uid (see worker.py:_host_user_flag) — stay owned by the host user.
ARG DIN_UID=1000
ARG DIN_GID=1000
RUN groupadd --gid "$DIN_GID" dinuser \
    && useradd --uid "$DIN_UID" --gid "$DIN_GID" --create-home --shell /bin/bash dinuser

USER dinuser
WORKDIR /home/dinuser

# dincli is a CLI, not yet a daemon (the `dind` daemon is a future phase). To
# keep a long-lived container that operators `docker compose exec` into, the
# main process just idles. When `dind` exists this CMD becomes its entrypoint.
CMD ["sleep", "infinity"]
