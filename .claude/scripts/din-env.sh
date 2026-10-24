# Machine-specific paths for the din-* skills. Source it: `source .claude/scripts/din-env.sh`.
# Every value can be overridden by exporting it first (e.g. in your shell profile).
# The defaults are the original maintainer's layout.

: "${DIN_REPO:=$HOME/projects/devnet}"   # main checkout of InfiniteZeroFoundation/DevNet
: "${DIN_WORK:=$HOME/tempdir/DIN}"       # review worktrees (PRs/), merge-fix logs, push-check worktree + logs
: "${DIN_NVM:=$HOME/.nvm/nvm.sh}"        # sourced for npm/npx if present (Node 20)

# Python 3.12 with torch and `pip install -e ".[test]"` of this repo.
if [ -z "${DIN_PY:-}" ]; then
  if [ -x "$HOME/my_venvs/torchenv/bin/python" ]; then
    DIN_PY=$HOME/my_venvs/torchenv/bin/python
  else
    DIN_PY=$(command -v python3)
  fi
fi

export DIN_REPO DIN_WORK DIN_PY DIN_NVM
