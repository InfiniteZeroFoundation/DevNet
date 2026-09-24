# DIN Indexer — GraphQL integration handoff

## What was done

The `dindao registry list-pending-requests` command (`dincli/cli/dindao.py`) previously
enumerated pending model and manifest requests by calling `totalModelRequests()` /
`totalManifestRequests()` on-chain and iterating through every index with an individual
RPC call per entry.  Those two `for idx in range(...)` loops have been replaced with
GraphQL queries to the locally-running subgraph.

### Integration point

| File | Location | Change |
|------|----------|--------|
| `dincli/cli/dindao.py` | top of file | Added `_SUBGRAPH_URL` constant and `_query_subgraph()` helper |
| `dincli/cli/dindao.py` | `list_pending_requests` — model block | GraphQL-first, RPC fallback |
| `dincli/cli/dindao.py` | `list_pending_requests` — manifest block | GraphQL-first, RPC fallback |

### Queries issued

**Model registration requests**
```graphql
{
  modelRegistrationRequests(where: { processed: false }, first: 1000) {
    requestId
    requester
    isOpenSource
    feePaid
  }
}
```

**Manifest update requests**
```graphql
{
  manifestUpdateRequests(where: { processed: false }, first: 1000) {
    requestId
    model { modelId }
    requester
    feePaid
  }
}
```

### Fallback behaviour

`_query_subgraph()` returns `None` on any of:

- `requests.exceptions.ConnectionError` / `Timeout` (graph-node not running)
- HTTP 4xx / 5xx response
- GraphQL `errors` field present in the response body

When `None` is returned, both blocks fall through to the original RPC enumeration loop,
so the command remains fully functional in environments where the subgraph is not deployed.

### Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `DIN_SUBGRAPH_URL` | `http://localhost:8000/subgraphs/name/din-protocol/graphql` | Override the subgraph endpoint (CI, staging, custom port) |

---

## Follow-up candidates

The same RPC-enumeration pattern appears in at least two other places.  These are
candidates for a P5 ticket once the subgraph schema is extended to cover task-level events:

| File | Approx. line | Description |
|------|-------------|-------------|
| `dincli/cli/modelownerd/lms.py` | ~62 | Iterates `totalLocalModelSubmissions()` to list LMS entries for the current GI |
| `dincli/cli/modelownerd/aggregation.py` | ~76, 95, 136 | Iterates T1/T2 batch entries to build aggregation payloads |

These loops touch `DINTaskCoordinator` state which is task-level (not covered by the
current platform-contract subgraph).  They should be migrated once dynamic data sources
for task contracts are added in a future subgraph version.

---

## Test coverage

`tests/test_list_pending_requests.py` adds six unit tests (no live node required):

| Test | What it verifies |
|------|-----------------|
| `test_graphql_model_path` | Two model requests returned from subgraph appear in output |
| `test_graphql_model_path_empty` | Empty subgraph response shows the "no pending" message |
| `test_graphql_manifest_path` | Manifest request with nested `model.modelId` renders correctly |
| `test_rpc_fallback_on_connection_error` | `ConnectionError` triggers RPC loop |
| `test_rpc_fallback_on_graphql_error_body` | `errors` in response body triggers RPC loop |
| `test_rpc_fallback_on_http_error` | HTTP 503 triggers RPC loop |

The existing integration test `test_din_rep_lists_pending_requests` in
`tests/dincli/test_03_registration.py` continues to exercise the command end-to-end
against a live Hardhat node (graph-node is not running in that environment, so the RPC
fallback path is exercised there automatically).
