# Differential Privacy Improvements

## Summary

This issue covers improvements to the differential privacy pipeline used by Infinite Zero Network during local client training and update submission.

The current implementation already introduces basic clipping and Gaussian noise, but it is still closer to a proof of concept than a production-ready privacy layer. The next step is to make differential privacy a configurable capability exposed through `dincli`, so model owners can choose a privacy strategy, tune its parameters, and generate service artifacts that match their deployment needs.

## manifest

The model manifest at [manifest.json](/home/azureuser/projects/devnet/cache_model_0/manifest.json) can be used to define differential privacy parameters for a task.

That means DP behavior should not be limited to hardcoded values inside `client.py`. A model owner should be able to place DP-related settings in the manifest and let services read them at runtime.

Example manifest fields:

```json
{
  "dp_mode": "afterTraining",
  "dp_sigma": 0.5,
  "dp_clipping_norm": 1.0,
  "dp_mechanism": "post_training_gaussian"
}
```

These parameters can be accessed inside services through the injected service runtime context:

```python

# Example of how to access DP parameters in a service from manifest:

def train_client_model_and_upload_to_ipfs(
    genesis_model_ipfs_hash,
    account_address,
    effective_network="local",
    initial_model_ipfs_hash=None,
    dp_mode=None,
    model_base_dir="",
    gi=None,
    runtime=None,
):
    if dp_mode is None and runtime is not None:
        dp_mode = runtime.get_manifest_key("dp_mode", "disabled")
    if dp_mode is None:
        dp_mode = "disabled"

    sigma = runtime.get_manifest_key("dp_sigma", 0.5) if runtime else 0.5
    clipping_norm = runtime.get_manifest_key("dp_clipping_norm", 1.0) if runtime else 1.0
    dp_mechanism = runtime.get_manifest_key("dp_mechanism", "post_training_gaussian") if runtime else "post_training_gaussian"
```

For example, a client service can resolve manifest-driven DP settings from `runtime` instead of hardcoding them or reloading manifest state manually:

```python
if dp_mode == "afterTraining" and dp_mechanism == "post_training_gaussian":
    noisy_state_dict = add_noise_and_clip_state_dict(
        original_state_dict,
        sigma,
        clipping_norm,
    )
```

This is why the runtime context was added: `dincli` resolves the manifest once for a service run, injects it into the service call, and lets service code read DP configuration through `runtime.get_manifest_key(...)`. That keeps privacy configuration in the manifest, makes service behavior easier to tune per model, and avoids coupling service code to CLI-side manifest lookup details.

## Why This Matters

Differential privacy helps reduce the risk that sensitive information can be inferred from model updates shared during federated learning.

For Infinite Zero Network, this matters because the protocol is intended to support:

- decentralized training across many participants
- validator-coordinated aggregation
- auditable reward and evaluation workflows
- future secure aggregation and privacy-preserving infrastructure

If privacy is only applied in a simplistic way, contributors cannot reason clearly about the trade-off between privacy and model utility, and the wider system cannot build reliable guarantees on top of it.

This also matters because the intended developer workflow is modular: model owners should be able to assemble service artifacts with different privacy options instead of editing low-level training code by hand.

## Product Direction

`dincli` is expected to become a tool that helps model owners build the service artifacts used in a deployment, such as:

- `aggregator.py`
- `auditor.py`
- `client.py`
- `model.py`
- `modelowner.py`

The goal is a modular workflow where a model owner can choose implementation options and parameters, generate the final service artifacts, and place those artifacts into the deployment manifest.

Within that workflow, differential privacy should be treated as a selectable capability rather than a single hardcoded implementation.

## Current State

Current implementation lives primarily in:

- `cache_model_0/services/client.py`
- `cache_model_0/services/model.py`

Related integration points include:

- `dincli/`
- aggregation workflows
- auditor workflows
- model-owner service generation workflows

The current approach roughly does the following:

1. Train the local model.
2. Clip model weights.
3. Add Gaussian noise.
4. Upload the resulting weights.

Representative logic today looks like:

```python
def add_noise(weights, sigma):
    noise = torch.normal(0, sigma, size=weights.shape, device=weights.device)
    return weights + noise

def clip_weights(weights, S):
    norm = torch.norm(weights)
    factor = max(1.0, norm / S)
    return weights / factor
```

## Main Limitations

### 1. Privacy Is Applied Only After Training

The current mechanism perturbs weights after local training completes.

That is simple to implement, but it is weaker and less principled than approaches such as:

- DP-SGD
- per-step clipping
- per-sample gradient clipping

### 2. No Privacy Accounting

The system does not currently report:

- epsilon (`ε`)
- delta (`δ`)
- privacy budget consumption
- accountant outputs over time

Without this, privacy claims are not measurable.

### 3. Static Hyperparameters

Parameters such as `sigma = 0.5` and `S = 1.0` are effectively hardcoded in the implementation. Those values should be configurable through the model manifest, code, config, or CLI inputs.

### 4. No Strategy Selection For Model Owners

There is no clear mechanism for a model owner to choose among multiple differential privacy approaches when building a service package.

The product direction should support selecting between strategies such as:

- no differential privacy
- weight-level noise after training
- update-level privacy
- DP-SGD
- future custom privacy modules

That choice should be explicit in `dincli` and preserved in the generated artifacts or manifest configuration.

### 5. Weight-Level Perturbation

The current implementation modifies raw model weights directly rather than working with:

- gradients
- local deltas
- layer-level updates

That makes experimentation harder and weakens the connection to standard DP training practice.

### 6. Limited System Integration

The privacy logic is not yet designed to fit future workflows such as:

- secure aggregation
- subgroup aggregation
- encrypted or masked updates
- validator-side privacy-aware evaluation

## Scope Of Work

Contributors should aim to improve the privacy pipeline while keeping the implementation practical for the current DevNet codebase.

Useful directions include:

- defining a `dincli` interface for selecting DP mechanisms during service generation
- replacing or extending post-training noise with a more principled DP method
- reading DP parameters from the model manifest in client services
- making parameters configurable through `dincli` and config files
- making those selections visible in generated service artifacts and manifests
- adding privacy accounting outputs
- benchmarking privacy versus model utility
- documenting trade-offs and operational assumptions

## Expected User Workflow

The intended workflow for a model owner should look roughly like this:

1. Define the model and service requirements.
2. Choose whether differential privacy is enabled.
3. Select a DP mechanism.
4. Set mechanism-specific parameters in the manifest.
5. Generate service artifacts with `dincli`.
6. Reference the generated artifacts in the model-owner manifest.

The issue is not only about the privacy math. It is also about designing a clean developer experience for selecting, configuring, and materializing privacy behavior.

## DP Strategy Selection

`dincli` should eventually support multiple differential privacy modes that a model owner can select during service generation.

Possible examples:

- `none`
- `post_training_gaussian`
- `update_gaussian`
- `dp_sgd`

Each mode should define:

- where privacy is applied
- which parameters are required
- which optional parameters are available
- whether privacy accounting is supported
- whether the mode is compatible with future aggregation strategies

## Parameterization

The tool should make it clear how parameters are chosen and applied.

Examples of parameters that may vary by DP strategy include:

- `sigma` or `noise_multiplier`
- `clipping_norm`
- `delta`
- target `epsilon`
- accountant type
- per-layer versus global clipping
- update-level versus gradient-level privatization

Contributors should think about both:

- the user-facing configuration model
- the internal implementation path that maps those settings into generated code or runtime configuration

## Configuration And Artifact Generation

One acceptable direction is for `dincli` to generate service artifacts from modular templates or configuration-driven builders.

For example, a model owner might choose:

- a client training strategy
- a DP mechanism
- aggregation behavior
- auditor behavior

That selection should then influence generated files such as:

- `client.py`
- `aggregator.py`
- `auditor.py`
- `modelowner.py`

The exact implementation can vary, but the result should make it clear:

- which DP mechanism is active
- which parameters were selected
- where the mechanism is applied
- what assumptions the generated service makes

## Suggested Tasks

### Beginner Tasks

#### Configurable DP Parameters

Move hardcoded privacy parameters into configuration or CLI options.

Example:

```yaml
dp:
  enabled: true
  mechanism: post_training_gaussian
  sigma: 1.0
  clipping_norm: 1.0
```

#### Better Logging

Expose useful training and privacy metadata, for example:

- clipping norm
- noise multiplier
- DP mode
- training accuracy
- privacy accountant status

#### CLI Support

Add flags in `dincli` so model owners can select privacy settings without patching code.

Example:

```bash
dincli build service \
  --service client \
  --dp post_training_gaussian \
  --sigma 1.0 \
  --clip-norm 1.0
```

#### Per-Layer Clipping

Replace a single global clipping pass with per-layer clipping, or at least make the clipping strategy swappable.

#### DP Mechanism Selection

Design a CLI or config interface that allows model owners to choose one DP mode from multiple supported implementations.

The first version does not need every mechanism fully implemented, but it should establish a clean extension model.

### Intermediate Tasks

#### Privacy Accounting

Integrate an accountant and expose measurable privacy outputs.

Candidate options:

- Opacus accountant
- Renyi DP accountant
- moments accountant

Example output:

```text
Privacy Budget:
epsilon = 4.82
delta = 1e-5
```

#### DP-SGD Integration

Evaluate or integrate a more standard private optimization flow.

Candidate options:

- Opacus
- TensorFlow Privacy
- custom DP-SGD implementation

Example:

```python
from opacus import PrivacyEngine

privacy_engine = PrivacyEngine()

model, optimizer, data_loader = privacy_engine.make_private(
    module=model,
    optimizer=optimizer,
    data_loader=data_loader,
    noise_multiplier=1.1,
    max_grad_norm=1.0,
)
```

#### Update-Level Differential Privacy

Instead of perturbing full model weights, compute and privatize the client update itself.

Example:

```python
local_update = local_model - global_model
```

#### Service Builder Integration

Connect DP strategy selection to the modular service-generation workflow so generated artifacts consistently reflect the chosen privacy behavior.

This may involve:

- config schema design
- template selection
- builder logic in `dincli`
- manifest-facing metadata

### Advanced Tasks

#### Secure Aggregation Compatibility

Research and prototype approaches that remain compatible with decentralized aggregation, such as:

- additive masking
- Bonawitz-style secure aggregation
- MPC-friendly update handling

#### Homomorphic Encryption Exploration

Investigate whether future privacy layers could work alongside encrypted aggregation approaches, for example:

- CKKS
- TenSEAL

#### Byzantine-Resistant Aggregation

Explore robust aggregation methods that pair well with private updates, such as:

- Krum
- median aggregation
- trimmed mean

#### Privacy-Aware Reward Evaluation

Investigate whether privacy metadata can inform:

- auditor-side validation
- reward scoring
- contributivity analysis

## Expected Deliverables

Contributors may submit one or more of the following:

- code improvements
- tests
- benchmarking results
- research notes
- documentation updates
- example experiments
- service-generation design proposals

## Definition Of A Good Contribution

A strong contribution to this issue should:

- improve the current privacy mechanism in a measurable way
- make DP selection understandable for model owners
- explain the privacy and utility trade-off clearly
- avoid hardcoded assumptions where configuration is more appropriate
- include tests or reproducible evaluation notes where possible
- fit the existing DevNet architecture rather than introducing isolated code
- align with a modular artifact-generation workflow in `dincli`

## Suggested Research Topics

| Topic | Description |
|---|---|
| DP-SGD | Proper private optimization |
| Adaptive Clipping | Dynamic clipping thresholds |
| Secure Aggregation | Privacy-preserving aggregation |
| Local vs Global DP | Compare approaches |
| Sparse Updates | Reduce communication overhead |
| Compression + DP | Quantization plus privacy |
| Personalized Privacy | Different budgets per client |
| Byzantine Robustness | Defend against malicious clients |

## Helpful Libraries

Differential privacy:

- Opacus
- TensorFlow Privacy

Cryptography and privacy tooling:

- PySyft
- TenSEAL
- PyCryptodome

Federated learning frameworks:

- Flower
- FedML

## Relevant Files

- `cache_model_0/services/client.py`
- `cache_model_0/services/model.py`
- `dincli/`
- aggregation-related services
- auditor-related services
- model-owner service builder logic

## Long-Term Alignment

This issue supports the broader goal of building decentralized AI systems where:

- users retain data ownership
- training happens collaboratively
- validators coordinate aggregation
- rewards remain transparent
- privacy guarantees become stronger and more measurable

It also supports a better developer experience where model owners can compose service behavior from explicit options and generate artifacts that are ready to place into a deployment manifest.

## How To Contribute

1. Review the current implementation in `cache_model_0/services/client.py`.
2. Identify where `dincli` should expose DP selection and parameter configuration.
3. Decide whether your contribution is implementation-focused, UX/config-focused, benchmarking-focused, or research-focused.
4. Keep changes scoped and measurable.
5. Add tests or documentation that explain the behavior you introduce.
6. Submit a pull request with a concise summary of the privacy improvement and its trade-offs.
