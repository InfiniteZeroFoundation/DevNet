#!/usr/bin/env bash
set -euo pipefail

mode=${1:-}
compile_args=()
case "$mode:$#" in
    :0|--check:1) ;;
    --upgrade:1) compile_args+=(--upgrade) ;;
    --upgrade-package:2) compile_args+=(--upgrade-package "$2") ;;
    *)
        echo "Usage: $0 [--check | --upgrade | --upgrade-package NAME]" >&2
        exit 2
        ;;
esac

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
lock=requirements/dincli-runtime.txt
require_lock() {
    if [[ ! -f "$lock" || -L "$lock" || ! -s "$lock" ]]; then
        echo "Expected a nonempty regular file at $lock" >&2
        exit 1
    fi
}
if [[ "$mode" == --check ]]; then
    git ls-files --error-unmatch -- "$lock" >/dev/null
    require_lock
fi

if [[ $(uname -s) != Linux ]]; then
    echo "Run this lock generator on Linux." >&2
    exit 1
fi

uv_version=0.10.9
index=https://pypi.org/simple
mkdir -p requirements
# Stage on the lock's filesystem so publishing the completed output is atomic.
tmp=$(mktemp -d requirements/.dincli-lock.XXXXXXXX)
tmp=$(cd "$tmp" && pwd)
trap 'rm -rf -- "$tmp"' EXIT

# Do not inherit private indexes, pip constraints, or tool configuration.
isolated=(env -i "PATH=$PATH" "HOME=$tmp" PIP_CONFIG_FILE=/dev/null)
"${isolated[@]}" python3 -m venv "$tmp/venv"
"${isolated[@]}" "$tmp/venv/bin/python" -m pip --isolated \
    --disable-pip-version-check install --quiet --no-deps --index-url "$index" "uv==$uv_version"

candidate="$tmp/dincli-runtime.txt"
if [[ -f "$lock" ]]; then
    cp -- "$lock" "$candidate"
fi
"${isolated[@]}" "$tmp/venv/bin/uv" --no-config pip compile pyproject.toml \
    --python-version 3.12 --universal --no-header --default-index "$index" \
    --output-file "$candidate" "${compile_args[@]}" >/dev/null
[[ -s "$candidate" ]]
{
    printf '# Generated from pyproject.toml by scripts/lock-dincli-runtime.sh (uv %s).\n' "$uv_version"
    cat -- "$candidate"
} > "$tmp/lock-with-header"
mv -- "$tmp/lock-with-header" "$lock"
require_lock

if [[ "$mode" == --check ]]; then
    git diff --exit-code -- "$lock"
fi
