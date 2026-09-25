#!/usr/bin/env bash
# Mirror .github/workflows/ci.yml locally on the exact commit about to be pushed
# to develop, in a dedicated worktree, so uncommitted WIP in the main checkout
# can't make a red commit look green (or the reverse).
#
# Usage: precheck.sh [--all] [<sha>]   (default <sha>: HEAD of the main checkout)
#   --all  run the Solidity job even if nothing under foundry/ or hardhat/ changed
set -uo pipefail

REPO=~/projects/devnet
WT=~/tempdir/DIN/push-check
PY=~/my_venvs/torchenv/bin/python
ALL=0
[ "${1:-}" = "--all" ] && { ALL=1; shift; }
SHA=$(git -C "$REPO" rev-parse "${1:-HEAD}") || exit 2
LOGDIR=~/tempdir/DIN/push-check-logs
mkdir -p "$LOGDIR"
LOG="$LOGDIR/${SHA:0:12}.log"
: > "$LOG"

step() {  # step <name> <cmd...>: run, log, stop on first failure
  local name=$1; shift
  echo "== $name" | tee -a "$LOG"
  if ( "$@" ) >>"$LOG" 2>&1; then
    echo "   ok" | tee -a "$LOG"
  else
    echo "   FAILED: $name (full log: $LOG)" | tee -a "$LOG"
    tail -n 40 "$LOG"
    exit 1
  fi
}

git -C "$REPO" fetch -q origin develop
if [ -d "$WT" ]; then
  git -C "$WT" checkout -q --detach -f "$SHA"
  git -C "$WT" clean -fdq -e node_modules -e foundry/lib -e cache -e out
else
  git -C "$REPO" worktree add -q --detach "$WT" "$SHA"
fi
cd "$WT" || exit 2

CHANGED=$(git diff --name-only origin/develop "$SHA")
echo "Checking ${SHA:0:12} ($(git log -1 --format=%s "$SHA"))"
echo "Commits ahead of origin/develop: $(git rev-list --count origin/develop.."$SHA")"

# Empty HOME, like the CI runner: catches tests that silently read
# ~/.config/dincli (how d321c2a's test passed locally and failed in CI).
CIHOME=$(mktemp -d)
trap 'rm -rf "$CIHOME"' EXIT

step "docs: relative link check" "$PY" .github/scripts/check_doc_links.py Documentation
step "python: dincli resolves to this worktree" \
  bash -c "cd '$WT' && '$PY' -c 'import dincli,sys; sys.exit(0 if dincli.__file__.startswith(\"$WT\") else 1)'"
step "python: pytest -m 'not integration'" \
  env HOME="$CIHOME" XDG_CONFIG_HOME="$CIHOME/.config" "$PY" -m pytest -m "not integration" -q -p no:cacheprovider

if [ $ALL = 1 ] || grep -qE '^(foundry|hardhat|\.github)/' <<<"$CHANGED"; then
  # shellcheck disable=SC1090
  source ~/.nvm/nvm.sh >/dev/null
  step "solidity: submodules" git submodule update --init --recursive -q
  step "solidity: foundry npm ci" bash -c "cd foundry && npm ci --silent"
  step "solidity: forge build (real via_ir profile, as CI)" bash -c "cd foundry && forge build"
  step "solidity: forge test" bash -c "cd foundry && forge test"
  step "solidity: hardhat npm ci" bash -c "cd hardhat && npm ci --silent"
  step "solidity: hardhat compile" bash -c "cd hardhat && npx hardhat compile"
  step "solidity: hardhat test" bash -c "cd hardhat && npx hardhat test"
else
  echo "== solidity: skipped (nothing under foundry/, hardhat/ or .github/ changed; pass --all to force)"
fi

echo "PRECHECK OK ${SHA}"
