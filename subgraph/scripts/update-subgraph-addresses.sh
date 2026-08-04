#!/usr/bin/env bash
# update-subgraph-addresses.sh
# Patches subgraph/subgraph.yaml's placeholder platform-contract addresses
# with the real addresses from a deployments JSON (foundry or hardhat schema).
#
# Usage:
#   ./scripts/update-subgraph-addresses.sh [path/to/deployments.json]
#
# Defaults to foundry/deployments/localhost.json, falling back to
# hardhat/deployments/localhost.json if the first doesn't exist.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBGRAPH_YAML="$SCRIPT_DIR/../subgraph.yaml"
REPO_ROOT="$SCRIPT_DIR/../.."

DEPLOYMENTS_JSON="${1:-}"
if [[ -z "$DEPLOYMENTS_JSON" ]]; then
  if [[ -f "$REPO_ROOT/foundry/deployments/localhost.json" ]]; then
    DEPLOYMENTS_JSON="$REPO_ROOT/foundry/deployments/localhost.json"
  elif [[ -f "$REPO_ROOT/hardhat/deployments/localhost.json" ]]; then
    DEPLOYMENTS_JSON="$REPO_ROOT/hardhat/deployments/localhost.json"
  else
    echo "error: no deployments JSON found. Deploy the platform contracts first" >&2
    echo "  (foundry: forge script script/DeployPlatform.s.sol ...," >&2
    echo "   hardhat: npx hardhat run scripts/deploy.ts --network localhost)" >&2
    echo "or pass an explicit path: $0 <path/to/deployments.json>" >&2
    exit 1
  fi
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required (https://jqlang.github.io/jq/)" >&2
  exit 1
fi

echo "Reading addresses from $DEPLOYMENTS_JSON"

# yaml "name:" value -> key in the deployments JSON. Plain array of pairs
# ("contract key") — associative arrays require bash 4, which macOS does not ship.
CONTRACT_KEY_PAIRS=(
  DINModelRegistry dinModelRegistry
  DinValidatorStake dinValidatorStake
  DinCoordinator dinCoordinator
  DinToken dinToken
)

TMP="$(mktemp)"
cp "$SUBGRAPH_YAML" "$TMP"

for ((i = 0; i < ${#CONTRACT_KEY_PAIRS[@]}; i += 2)); do
  contract="${CONTRACT_KEY_PAIRS[$i]}"
  key="${CONTRACT_KEY_PAIRS[$i + 1]}"
  address="$(jq -r --arg k "$key" '.[$k] // empty' "$DEPLOYMENTS_JSON")"
  if [[ -z "$address" ]]; then
    echo "error: key '$key' not found in $DEPLOYMENTS_JSON" >&2
    rm -f "$TMP"
    exit 1
  fi

  # Scope the replacement to this data source's block: find "name: <contract>",
  # then the next "address:" line after it, and patch only that one line.
  name_line="$(grep -n "name: $contract\$" "$TMP" | head -1 | cut -d: -f1)"
  if [[ -z "$name_line" ]]; then
    echo "warning: data source '$contract' not found in subgraph.yaml, skipping" >&2
    continue
  fi
  offset="$(tail -n "+$name_line" "$TMP" | grep -n "address:" | head -1 | cut -d: -f1)"
  address_line=$((name_line + offset - 1))

  sed -i.bak "${address_line}s|address: \".*\"|address: \"$address\"|" "$TMP"
  rm -f "$TMP.bak"
  echo "  $contract -> $address"
done

mv "$TMP" "$SUBGRAPH_YAML"
echo "Updated $SUBGRAPH_YAML"
