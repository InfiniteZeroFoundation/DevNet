# InfiniteZero Network — DevNet

<div align="center">

[![CI](https://github.com/InfiniteZeroFoundation/DevNet/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/InfiniteZeroFoundation/DevNet/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-brightgreen?style=flat)](LICENSE)
[![Good first issues](https://img.shields.io/github/issues/InfiniteZeroFoundation/DevNet/good%20first%20issue?label=good%20first%20issues&color=7057ff)](https://github.com/InfiniteZeroFoundation/DevNet/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22good%20first%20issue%22)
[![Telegram](https://img.shields.io/badge/chat-Telegram-26A5E4?style=flat&logo=telegram&logoColor=white)](https://t.me/+h46VS3AnO384ZGI8)
![Built on Ethereum](https://img.shields.io/badge/Built%20on-Ethereum-3C3C3D?style=flat&logo=ethereum&logoColor=white)
![Founded at Oxford](https://img.shields.io/badge/Founded%20at-University%20of%20Oxford-002147?style=flat)

</div>

> The internet gave everyone a voice.\
> Open source gave everyone a tool.\
> Yet AI learns from only a fraction of the world's data.
>
> **InfiniteZero lets AI learn from the rest — where it lives, for everyone.**

---

## What is this?

InfiniteZero is building **DIN** (Decentralized Intelligence Network), an open protocol for training shared AI models on data where it lives. Participants train models on their own devices with federated learning and share **model updates, not raw data**. Smart contracts on Ethereum coordinate each training round, check the work, and reward the people who do it.

This repository is the **DevNet**: the smart contracts, the `dincli` command-line tool, the reference model services, and the documentation for everyone building on or running the network.

**Where we are today**

- **DevNet 2.0 is live and experimental**, on the Optimism Sepolia test network, using test ETH. Validator nodes run 24/7 from Japan to Canada. Expect bugs, changes and resets.
- **One tested example so far:** an MNIST image model runs end to end. Other model types are supported by design but not yet tested.
- **Next:** a public testnet, then mainnet with a fully decentralised fair launch, with no ICO and no VC allocation.
- **Privacy:** raw data stays on devices. Optional differential-privacy settings exist but are off by default and still being strengthened, so we make no formal privacy guarantee yet.
- **Governance:** decisions are made in the open today; on-chain community governance is planned after mainnet.

---

## Start here

| You want to… | Go to |
| :--- | :--- |
| **Run a node or join a training round** | [Getting started on DevNet](Documentation/public/getting-started.md) |
| **Install and configure `dincli`** (including IPFS) | [Setup guide](Documentation/public/setup.md) |
| **Train your own model on the network** | [What can I train on DIN?](Documentation/public/what-can-be-trained.md) |
| **Evaluate DIN for your community or organisation** | [Partner introduction](Documentation/public/partner-introduction.md) |
| **Contribute code, docs, research or translations** | [Good first issues](https://github.com/InfiniteZeroFoundation/DevNet/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22good%20first%20issue%22) · [Contributing guide](Developer/CONTRIBUTING.md) · [Roadmap](Developer/ROADMAP.md) |

All documentation: [`Documentation/`](Documentation/README.md)

---

## What's in this repository

| Folder | Contents |
| :--- | :--- |
| `foundry/` | Solidity smart contracts (staking, slashing, rewards, emission, fair-launch distribution) and their test suite |
| `dincli/` | The `dincli` command-line tool used by validators, clients and model owners |
| `cache_model_0/` | The reference MNIST model and its training, auditing and aggregation services |
| `Documentation/` | What exists today: `public/` for participants, `technical/` for code readers and auditors |
| `Developer/` | Plans, designs, tasks and process docs, including the [roadmap](Developer/ROADMAP.md) and [backlog](Developer/BACK_LOG.md) |

Every change is reviewed by someone other than its author, and CI runs the full contract and Python test suites on every push.

---

## Contributing

The network is open and experimental. We work on the `develop` branch, and no contribution is too small: documentation, testing, tooling, smart contracts, privacy research and translations all matter.

1. Pick a [good first issue](https://github.com/InfiniteZeroFoundation/DevNet/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22good%20first%20issue%22) or a [help wanted](https://github.com/InfiniteZeroFoundation/DevNet/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22help%20wanted%22) issue, and comment to claim it.
2. Read the [contributing guide](Developer/CONTRIBUTING.md) and [development setup](Developer/DEVELOPMENT_SETUP.md).
3. Branch off `develop` and open your pull request against `develop`.

Questions? Ask in [Telegram](https://t.me/+h46VS3AnO384ZGI8) or [say hello in Discussions](https://github.com/InfiniteZeroFoundation/DevNet/discussions/92).

Found a security issue? Please don't open a public issue. See our [security policy](https://github.com/InfiniteZeroFoundation/.github/blob/main/SECURITY.md).

---

## Learn more and support the work

- 📄 [White Paper](https://github.com/InfiniteZeroFoundation/White-Paper)
- 📊 [Impact and traction](IMPACT.md)
- ❤️ [Support the network on Giveth](https://giveth.io/project/infinitezero-network)
- ✉️ [Partnerships and grants](mailto:abrahamnash@protonmail.com)

If you use this software in research, please cite it using the **"Cite this repository"** button on the right.

---

<div align="center">

*InfiniteZero Foundation — open AI infrastructure, built by everyone, for everyone.*\
*Open protocol · Built in the open · Apache-2.0 · © 2026*

</div>
