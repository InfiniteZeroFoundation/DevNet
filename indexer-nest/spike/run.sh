#!/bin/sh
# The whole run the views are checked against, on a fresh anvil from DevNet's ./foundry/anvil.sh:
#   spike  - platform, one model, GI 1 to local-model submissions (NuthatchSpike.s.sol)
#   gi     - GI 1 on to GIended, three stages with blocks mined between (NuthatchGI.s.sol)
#   gov    - the owner-side governance calls (NuthatchGov.s.sol)
# Usage: spike/run.sh   (foundry and anvil on PATH; DEVNET defaults to the repo root two levels up)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
RPC=${RPC:-http://127.0.0.1:8545}
SENDER=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
DEVNET=${DEVNET:-$(cd "$HERE/../.." && pwd)}
cd "$DEVNET/foundry"
trap 'rm -f "$DEVNET"/foundry/script/NuthatchSpike.s.sol "$DEVNET"/foundry/script/NuthatchGI.s.sol "$DEVNET"/foundry/script/NuthatchGov.s.sol' EXIT
for s in NuthatchSpike NuthatchGI NuthatchGov; do cp "$HERE/$s.s.sol" script/; done
forge clean   # old build-info copies make the upgrades plugin refuse "multiple contracts"
run() { forge script "script/$1.s.sol" --sig "$2" --rpc-url "$RPC" --broadcast --unlocked --sender "$SENDER" >/dev/null; echo "$1 $2 done"; }
run NuthatchSpike "spike()"
run NuthatchGI "stage1()"; cast rpc anvil_mine 10 --rpc-url "$RPC" >/dev/null
run NuthatchGI "stage2()"; cast rpc anvil_mine 10 --rpc-url "$RPC" >/dev/null
run NuthatchGI "stage3()"
run NuthatchGov "gov()"
