# Model Owner Service Builder

## Summary

DevNet already expects a model owner to provide service artifacts such as:

- `aggregator.py`
- `auditor.py`
- `client.py`
- `model.py`
- `modelowner.py`

Those files are then uploaded to IPFS and referenced from the model manifest.

What is missing today is a tooling layer that helps a model owner build those services in a modular way instead of hand-editing Python for every deployment. The intended direction is a service builder in `dincli` that lets a model owner choose options, set parameters, generate the final artifacts, and place those outputs into the manifest workflow.

## Problem

The current developer experience is too manual:

- model owners start from template service files
- behavior is often hardcoded inside Python services
- feature choices such as privacy mode, client training policy, scoring logic, or aggregation strategy are not first-class configuration inputs
- changing behavior usually means editing code directly
- manifest wiring happens after the fact instead of being part of service generation

That approach does not scale once DevNet supports multiple training, privacy, aggregation, and auditing modes.

## Goal

Provide a tool that generates service artifacts for a model owner from explicit configuration choices.

The tool should let a model owner:

1. choose which service files to generate
2. select implementation modules for each role
3. set parameters for the selected modules
4. generate the final Python artifacts
5. surface the generated artifact paths and manifest-ready entries

The output should remain compatible with the existing service and manifest model documented in `Documentation/services.md` and `Documentation/manifest.md`.

## Expected Inputs

The service builder should support a configuration model where the model owner can select role-specific behavior.

Examples:

- client training mode
- differential privacy mode
- optimizer and training hyperparameters
- auditor scoring method
- aggregation strategy
- model owner evaluation and audit-batch behavior
- dependency set for each stakeholder role

Example configuration shape:

```yaml
model:
  name: mnist-digits
  framework: pytorch

services:
  client:
    training_mode: supervised
    dp:
      enabled: true
      mechanism: post_training_gaussian
      sigma: 1.0
      clipping_norm: 1.0
  auditor:
    scoring: accuracy
  aggregator:
    strategy: fedavg
  modelowner:
    audit_data_split: fixed_percentage
    audit_data_percentage: 5
```

## Generated Outputs

The tool should be able to materialize a service package containing:

- `services/client.py`
- `services/auditor.py`
- `services/aggregator.py`
- `services/modelowner.py`
- `services/model.py`
- optional `requirements.txt` artifacts per role
- manifest-ready metadata for each generated service

The result should be suitable for placement under a task directory such as:

```text
tasks/<network>/<task_coordinator_address>/
```

with service files referenced by the manifest in the current format:

```json
"train_client_model_and_upload_to_ipfs": {
  "type": "custom",
  "path": "services/client.py",
  "ipfs": "<cid>",
  "stakeholders": ["clients"]
}
```

## Core Capabilities

### 1. Modular Service Composition

Each role should be built from selectable modules rather than one fixed template.

Examples:

- client service: supervised training, semi-supervised training, DP-enabled training
- auditor service: accuracy scoring, robust scoring, future benchmark suites
- aggregator service: FedAvg, weighted averaging, robust aggregation
- model owner service: genesis generation, audit batch generation, custom scoring

### 2. Parameter Injection

The selected module should receive its parameters through a defined config layer, not by requiring manual code edits after generation.

Examples:

- DP parameters
- epoch count
- optimizer settings
- audit batch size
- score thresholds
- aggregation weights or rules

### 3. Artifact Generation

The tool should generate final Python files that are ready to upload and use. This can be implemented with:

- templates with placeholders
- feature composition over base service skeletons
- config-driven code generation
- a hybrid approach where shared runtime helpers are imported by generated service stubs

The exact generation method is less important than producing stable, readable artifacts.

### 4. Manifest Integration

The tool should not stop at file generation. It should also help the model owner connect outputs into the manifest by:

- producing manifest entry snippets
- optionally patching a local `manifest.json`
- surfacing required IPFS upload steps
- showing which stakeholders depend on which artifacts

### 5. Validation

Before generation completes, the tool should validate:

- required parameters are present
- selected modules are compatible
- manifest-required functions will exist in generated files
- output paths are consistent with the expected task layout

## Proposed Workflow

1. Model owner chooses a base model and task setup.
2. Model owner selects service modules for `client`, `auditor`, `aggregator`, and `modelowner`.
3. Model owner sets module-specific parameters.
4. `dincli` generates the service artifacts.
5. Generated artifacts are reviewed locally.
6. Artifacts are uploaded to IPFS.
7. The resulting CIDs are inserted into `manifest.json`.
8. The manifest is uploaded and used in the normal model-owner flow.

## CLI Direction

One reasonable CLI direction is:

```bash
dincli build services \
  --config service-builder.yaml \
  --output tasks/local/<task_coordinator_address>
```

Additional commands could include:

```bash
dincli build services --service client --list-modes
dincli build services --service auditor --describe accuracy
dincli build services --config service-builder.yaml --write-manifest
```

## Architecture Direction

A practical implementation can be split into four layers:

### 1. Service Module Registry

Defines the available strategies for each role and the parameters each strategy accepts.

### 2. Builder Configuration Schema

Defines the validated user-facing config or CLI flags used to select behavior.

### 3. Artifact Generator

Produces the actual service files and optional requirements artifacts.

### 4. Manifest Writer

Converts generated outputs into manifest-ready entries aligned with the current schema.

## Near-Term Scope

A first usable version does not need to solve every service variation. It should focus on a narrow but real slice:

- generate `client.py`, `auditor.py`, `aggregator.py`, and `modelowner.py`
- support a small number of selectable strategies
- expose key parameters through config
- emit manifest-ready service entries
- keep compatibility with existing `dincli` and task directory conventions

Good initial strategy choices:

- client: `supervised`, `supervised_dp`
- auditor: `accuracy`
- aggregator: `fedavg`
- modelowner: `default`

## Why This Matters

This tooling makes DevNet more than a static template repository.

It moves the platform toward:

- reusable service generation
- clearer model-owner workflows
- explicit feature selection
- better manifest hygiene
- easier experimentation across privacy, training, aggregation, and scoring modes

In practice, this is the missing layer between protocol templates and a real model-owner product experience.
