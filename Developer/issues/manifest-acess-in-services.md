# Manifest Access In Services

## Summary

This issue is about how custom service functions should access manifest data at runtime.

Today `dincli` dynamically loads service functions from task-specific files such as:

- `cache_model_0/services/client.py`
- `cache_model_0/services/auditor.py`
- `cache_model_0/services/aggregator.py`
- `cache_model_0/services/modelowner.py`

Those services are meant to be customizable and manifest-driven. However, in practice, manifest access is still controlled from the CLI layer. That creates a gap between the documented flexibility of services and what service code can actually do cleanly.

## Problem Statement

The current architecture allows `dincli` to load custom functions through `ctx.obj.load_custom_fn()`, but the loaded service code does not receive a standard runtime context for reading manifest values.

This becomes a problem when a service needs to read custom manifest fields dynamically, for example:

- training hyperparameters
- model-specific paths
- custom feature flags
- aggregation settings
- auditor thresholds
- differential privacy parameters
- task-specific metadata defined by a model owner

There is already a helper in `dincli.cli.utils`:

- `get_manifest_key(network, key, model_id=None, task_coordinator_address=None)`

And the documentation in `Documentation/manifest.md` says custom manifest fields can be accessed in services through `get_manifest_key`.

But there is a practical issue:

- `get_manifest_key` requires runtime identifiers such as `network`, `model_id`, or `task_coordinator_address`
- those values are usually known in the CLI command flow, not inside the service module itself
- service functions loaded by `load_custom_fn()` do not receive a standard context object that carries those values

As a result, service authors either have to:

- hardcode behavior in the service function name or file layout
- duplicate configuration outside the manifest
- rely on implicit globals or directory assumptions
- add ad hoc parameters differently for each service entrypoint

That is not a clean production design.

## Current State

Relevant code paths today:

- `dincli/cli/context.py`
  - `load_custom_fn()` dynamically imports a function from a service file
- `dincli/cli/utils.py`
  - `get_manifest_key()` reads manifest data from cache or task directories
- `Documentation/manifest.md`
  - states that custom manifest fields can be accessed in services

The current loading mechanism returns a callable, but does not inject:

- `network`
- `model_id`
- `task_coordinator_address`
- manifest path
- parsed manifest contents
- a service runtime helper

So the service is loaded successfully, but it still lacks a standard way to discover its manifest context.

## Why This Matters

This limitation reduces the main value of custom services.

Without safe manifest access inside services:

- service code becomes less reusable across tasks
- simple customizations turn into CLI changes
- manifest-driven behavior becomes partially hardcoded
- documentation promises more flexibility than the runtime actually provides
- debugging becomes harder because service behavior depends on hidden calling conventions

It also creates a boundary problem:

- the CLI layer knows the runtime identity of the task
- the service layer contains the task-specific logic
- but there is no formal contract between them for configuration access

That missing contract is the root issue.

## What A Good Solution Should Provide

Any fix should support the following:

1. Services can read manifest values without hardcoding model-specific assumptions.
2. The runtime contract is explicit and consistent across client, auditor, aggregator, and model owner services.
3. The service does not need to reconstruct task identity from fragile directory conventions.
4. The approach works for both model-based manifests (`model_id`) and task-based manifests (`task_coordinator_address`).
5. The manifest access path is testable and easy to mock.
6. The design does not tightly couple custom services to internal CLI implementation details.

## Suggested Solutions

### Option 1: Import `get_manifest_key()` Directly Inside Services

Example direction:

```python
from dincli.cli.utils import get_manifest_key
```

Then service code would call it directly when needed.

### Benefits

- minimal code change
- easy to adopt quickly
- keeps manifest lookup logic in one existing helper

### Problems

- the service still needs `network` and `model_id` or `task_coordinator_address`
- there is no standard source for those values inside the service
- this couples service code to `dincli.cli.utils`, which is a CLI-oriented module
- it makes service code depend on a larger utility layer than necessary
- it does not define a proper runtime interface

This is acceptable as a temporary workaround, but not as the long-term design.

### Option 2: Pass `network` and `model_id` Into Every Service Function

Example direction:

```python
fn(..., network=effective_network, model_id=model_id)
```

### Benefits

- explicit
- easy to understand
- avoids hidden globals

### Problems

- every service function signature must change
- different commands may pass slightly different context values
- some flows use `task_coordinator_address` instead of `model_id`
- entrypoints become inconsistent unless standardized carefully
- future additions such as manifest path, role, cache directory, or logger will keep expanding signatures

This is better than Option 1, but it does not scale well.

### Option 3: Inject A Parsed Manifest Object Into Service Calls

Example direction:

```python
fn(..., manifest=manifest_data)
```

### Benefits

- simple for service authors
- avoids repeated file reads
- decouples service logic from manifest lookup implementation

### Problems

- the function loses access to the manifest identity and source metadata unless more fields are also passed
- stale data handling becomes the CLI's responsibility
- every caller must remember to pass the manifest
- service code may still need helper methods for nested lookups, validation, and defaults

This is a reasonable intermediate design, but still incomplete for a production runtime contract.

### Option 4: Introduce A Service Runtime Context Object

Example direction:

```python
class ServiceRuntimeContext:
    network: str
    model_id: int | None
    task_coordinator_address: str | None
    manifest_path: Path
    manifest: dict

    def get_manifest_key(self, key: str, default=None):
        ...
```

Then loaded service functions would receive:

```python
fn(..., runtime=service_runtime)
```

### Benefits

- explicit and extensible
- one standard runtime contract for all services
- manifest access is simple and local to the service
- future runtime features can be added without breaking every function signature
- easier unit testing because the runtime object can be mocked
- better separation between CLI orchestration and service logic

### Problems

- requires coordinated refactor of service entrypoints
- needs a compatibility strategy for existing services

This is the strongest architectural direction.

## Recommended Industry-Grade Production Solution

The production-grade solution is to introduce a formal service execution context and treat manifest access as part of that interface, not as an incidental helper import.

## Proposed Design

### 1. Add A Stable Runtime Interface

Create a small runtime object for dynamically loaded services, for example:

```python
class ServiceRuntimeContext:
    def __init__(
        self,
        network,
        model_id=None,
        task_coordinator_address=None,
        manifest_path=None,
        manifest=None,
        role=None,
    ):
        self.network = network
        self.model_id = model_id
        self.task_coordinator_address = task_coordinator_address
        self.manifest_path = manifest_path
        self.manifest = manifest or {}
        self.role = role

    def get_manifest_key(self, key, default=None):
        return self.manifest.get(key, default)
```

This object should be owned by the service/runtime layer, not by ad hoc command code.

### 2. Resolve Manifest Once In The CLI Layer

The CLI command already knows the effective runtime identity:

- network
- model id
- task coordinator address

It should resolve the correct manifest once, then pass that resolved manifest into the service runtime context.

That gives:

- one authoritative manifest snapshot per invocation
- fewer repeated file reads
- cleaner error handling
- a single place for freshness checks and cache policy

### 3. Pass The Runtime Context Into All Custom Service Entry Points

Instead of only loading a bare callable, define a standard calling convention for manifest-aware services.

For example:

```python
fn(..., runtime=runtime)
```

This preserves flexibility while avoiding a growing list of positional and keyword parameters.

### 4. Keep Backward Compatibility Temporarily

To avoid breaking existing custom services immediately:

- detect whether the loaded function accepts `runtime`
- pass it when supported
- keep legacy invocation behavior for older services during a transition period

That makes adoption incremental.

### 5. Move Manifest Helpers Out Of `dincli.cli.utils` If Needed

If service code needs shared manifest helpers, they should live in a runtime-safe module such as:

- `dincli.services.runtime`
- `dincli.services.manifest`

This avoids making custom services depend on CLI-oriented utility code.

## Why This Is Better Than Direct `get_manifest_key()` Imports

A direct import solves only the lookup function location. It does not solve runtime identity, interface stability, or testability.

A runtime context solves:

- where the manifest comes from
- how it is accessed
- how service code receives task identity
- how future execution metadata is added

That is the difference between a convenience patch and a maintainable production design.

## Additional Production Concerns

If this is implemented for real production use, the design should also address:

- manifest schema validation before service execution
- clear errors when required keys are missing
- immutable or read-only manifest access during execution
- versioning of the service runtime contract
- structured logging for service-level manifest access failures
- test fixtures for runtime context injection

These are important because once custom services become the main extension mechanism, the runtime contract becomes part of the platform API.

## Suggested Next Steps

1. Decide whether the short-term goal is a workaround or a proper runtime contract.
2. If short-term, allow `runtime` injection while keeping old service signatures working.
3. Add a small `ServiceRuntimeContext` implementation and use it in one service path first.
4. Update documentation so it reflects the actual supported pattern for manifest access.
5. Migrate sample services in `cache_model_0/services/` to the new interface.

## Conclusion

Yes, services should be able to access manifest data in a flexible way.

But the correct solution is not just "import `get_manifest_key()` from inside the service". The real requirement is a formal runtime contract that gives services safe access to manifest data and task identity.

For production-quality architecture, the recommended solution is:

- resolve manifest context in the CLI layer
- inject a standard runtime context into service functions
- expose manifest access through that runtime object

That keeps services flexible, testable, and aligned with the manifest-driven design the platform is already aiming for.
