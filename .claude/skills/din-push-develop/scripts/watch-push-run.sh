#!/usr/bin/env bash
# Wait for the GitHub Actions `push` run of <sha> on develop to finish.
# Meant for Bash run_in_background: prints one final line and exits.
#   exit 0  RESULT success <url>
#   exit 1  RESULT <failure|cancelled|...> <url>
#   exit 3  NO_RUN <sha>     (no push run appeared within ~5 minutes)
set -uo pipefail
SHA=$1
REPO=InfiniteZeroFoundation/DevNet

id=""
for _ in $(seq 1 20); do
  id=$(gh run list -R "$REPO" --commit "$SHA" --event push --workflow CI \
         --json databaseId --jq '.[0].databaseId' 2>/dev/null || true)
  [ -n "$id" ] && break
  sleep 15
done
[ -z "$id" ] && { echo "NO_RUN $SHA"; exit 3; }

gh run watch -R "$REPO" "$id" --interval 30 >/dev/null 2>&1 || true
read -r concl url < <(gh run view -R "$REPO" "$id" --json conclusion,url --jq '"\(.conclusion) \(.url)"')
echo "RESULT $concl $url"
[ "$concl" = "success" ]
