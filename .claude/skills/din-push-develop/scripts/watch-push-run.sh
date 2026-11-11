#!/usr/bin/env bash
# Wait for the GitHub Actions `push` run of <sha> on develop to finish.
# Meant for Bash run_in_background: prints one final line and exits.
#   exit 0  RESULT success <url>
#   exit 1  RESULT <failure|cancelled|...> <url>
#   exit 3  NO_RUN <sha>     (no push run appeared within ~5 minutes)
#   exit 4  WATCH_ERROR <url> <last status|unreachable>
#           (couldn't read a final conclusion: GitHub unreachable for ~10 min,
#           or the run still not completed after ~90 min -- NOT a CI verdict)
#
# Polls `gh run view` rather than relying on `gh run watch`: a transient
# network error (e.g. TLS handshake timeout) makes `gh run watch` exit early,
# and reading `conclusion` of a still-running run returns "", which used to be
# reported as a failure.
set -uo pipefail
SHA=$1
REPO=InfiniteZeroFoundation/DevNet
POLL=${WATCH_POLL:-30}              # seconds between polls
MAX_ERRORS=${WATCH_MAX_ERRORS:-20}  # consecutive failed gh calls before giving up (~10 min)
DEADLINE=$((SECONDS + 90 * 60))

id=""
for _ in $(seq 1 20); do
  id=$(gh run list -R "$REPO" --commit "$SHA" --event push --workflow CI \
         --json databaseId --jq '.[0].databaseId' 2>/dev/null || true)
  [ -n "$id" ] && break
  sleep 15
done
[ -z "$id" ] && { echo "NO_RUN $SHA"; exit 3; }
url="https://github.com/$REPO/actions/runs/$id"

errors=0
status=unreachable
while [ "$SECONDS" -lt "$DEADLINE" ]; do
  if out=$(gh run view -R "$REPO" "$id" --json status,conclusion \
             --jq '"\(.status) \(.conclusion)"' 2>/dev/null); then
    errors=0
    read -r status concl <<<"$out"
    if [ "$status" = "completed" ]; then
      echo "RESULT ${concl:-unknown} $url"
      [ "$concl" = "success" ]; exit $?
    fi
  else
    errors=$((errors + 1))
    if [ "$errors" -ge "$MAX_ERRORS" ]; then
      echo "WATCH_ERROR $url unreachable"; exit 4
    fi
  fi
  sleep "$POLL"
done
echo "WATCH_ERROR $url $status"; exit 4
