# Explore DIN with your community

DIN is an experimental network for training shared AI models across different people and organizations. In its reference workflow, contributors train on their own devices and share model updates, while independent participants check and combine those updates. This can help a community learn from data held in different places without collecting everyone's raw training data in one place. A project's own code and data handling still need review: model updates can reveal information, and keeping raw data local is not an automatic privacy guarantee.

> **Current scope:** This page describes DevNet 2.0 as represented by the code on `develop`. The [Getting Started guide](getting-started.md) covers the current public Model_0 example on Optimism Sepolia, which may differ. DIN is an experimental testnet project; participation terms and parameters can change.

## Why take part?

Your community may have a model it wants to improve using data that members cannot or do not want to pool. You may also want to test how shared training works, help improve the tools, or give feedback while the network is still taking shape. The [guide to what can be trained](what-can-be-trained.md) explains which path has been tested and what a new project would need to build.

Participation is an opportunity to experiment and contribute. It is **not** a promise of income, a future token allocation, or a particular model result.

## Ways to participate

| Your role | What you would do |
|---|---|
| **Client** | Train a model on your local data and submit a model update. You can contribute to an existing project without starting one yourself. |
| **Auditor** | Evaluate submitted models using test data supplied for the project. |
| **Aggregator** | Combine accepted updates into a new shared model. |
| **Model owner** | Bring a training project, prepare the model and evaluation method, and coordinate its training rounds and participants. |
| **Developer or tester** | Improve the protocol, command-line tools, documentation, or tests. See [Contributing](../../Developer/CONTRIBUTING.md). |

Auditors and aggregators are **validators**. They lock DIN test tokens as a stake and can lose part of it if they fail certain duties. Clients do not need to stake to train in the reference workflow. A person or organization can take more than one role, using separate accounts where the workflow requires them.

## What would your team need?

- **Time during a training round.** The model owner opens and closes each stage. Clients, auditors, and aggregators need to be available when their stage is active; this is not yet a hands-off service with a guaranteed schedule.
- **A computer suited to the project.** The tested handwritten-digit example lists a standard CPU, 4 GB RAM, and about 30 GB of disk space. These are **Model_0-only starting figures**, not requirements for every project. Larger models may need far more memory, storage, computing power, and network bandwidth. See [Getting Started](getting-started.md).
- **Basic setup.** Participants use Python 3.12 or later, the `dincli` command-line tool, a wallet, and access to IPFS for model files. The current public Model_0 example uses Optimism Sepolia test ETH for transactions; confirm the network details for any new trial. Start with [Setup](setup.md), [Wallet Setup](guides/wallet-setup.md), and [IPFS Setup](guides/ipfs.md). Use an encrypted keystore and review any project-provided code before running it.
- **Test tokens and operating costs.** Validators obtain DIN test tokens by depositing test ETH and must meet the current minimum stake. Model owners pay registration fees; open-source and proprietary projects have different fees. Blockchain transactions use test ETH. The token and fee values can change, and running hardware or storage can have real costs. Check the [role guides](roles/model-owner.md) and current network values before committing resources.

The only end-to-end training example identified so far is Model_0, which recognizes handwritten digits. A new model or dataset needs project-specific training, scoring, and aggregation code and a full trial run. [What can I train on DIN?](what-can-be-trained.md) walks through that fit check.

## From interest to a first training round

1. **Choose your role and project.** Join an existing model as a client, auditor, or aggregator, or describe a project you want to bring as a model owner.
2. **Discuss the trial.** Share your model goal, the kind of data contributors hold, the people and devices available, and any privacy constraints. Confirm who will coordinate the round and support onboarding.
3. **Set up and test.** Follow the guides for your role, prepare a wallet and test tokens, and try the Model_0 path before running a new project. Validators must stake before joining their role's registration stage.
4. **Join a round.** The model owner schedules the stages; clients train, auditors check submissions, and aggregators produce the next model. The [model workflow](workflows/model-workflow.md) has the full sequence.

## What is settled, and what is still being decided?

| Topic | Current position |
|---|---|
| **Fees** | **In the code:** model registration and manifest updates have separate fees for open-source and proprietary projects. The amounts can be changed. Fee-routing code exists; check the selected deployment before assuming a particular destination for payments. |
| **Validator rewards** | **Not yet a reliable participation promise:** reward and emission mechanisms exist in the code, but the testnet schedule and amounts are still being set in [issue #155](https://github.com/InfiniteZeroFoundation/DevNet/issues/155). Do not budget for a particular payout. |
| **Slashing** | **In the code, with parameters under review:** auditors and aggregators can lose stake for specified failures. The exact fractions and other testnet settings are still being reviewed in [issue #155](https://github.com/InfiniteZeroFoundation/DevNet/issues/155). Review the rules for your model before staking. |
| **Future token distribution** | **Direction, not an offer:** the team is developing a fair-launch distribution for validators and active participants, with no ICO, pre-sale, or VC allocation in the current plan. A claim contract exists, but eligibility rules and amounts have not been set; see [issue #75](https://github.com/InfiniteZeroFoundation/DevNet/issues/75). Testnet participation does **not** currently guarantee eligibility. |
| **Testnet resets** | **Open:** whether balances, stakes, models, or participation records carry over between testnet versions has not been confirmed. Treat testnet assets and state as temporary. |

The network is still experimental. Bugs, interruptions, changed parameters, and resets are possible. The current code and example do not establish a production security audit or guarantee that model-owner code is safe. New models and manifest changes pass a registry approval step before they take effect, but participants should still inspect the code and dependencies they run.

## Start a conversation

If your community wants to try DIN, [email the team](mailto:abrahamnash@protonmail.com). Say which role interests you, what kind of project or data you have, how many people may participate, and any hardware or privacy constraints. This gives the team a starting point for discussing a suitable trial. You can explore the public [Getting Started guide](getting-started.md) in the meantime. For bugs or questions while testing DevNet 2.0 code, use the separate [pre-launch discussion](https://github.com/InfiniteZeroFoundation/DevNet/discussions/102).
