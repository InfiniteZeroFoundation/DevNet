# Development Setup

This file is the minimal setup entrypoint for contributors working on DevNet.

**Prerequisite:** [Wallet Setup](../Documentation/public/guides/wallet-setup.md) — for development, use demo mode or `ETH_PRIVATE_KEY_<n>` in `.env`. Never commit real keys.

## Local Python Setup

```bash
git checkout develop
pip install -e .
```

If you are working on the ML or DP service code, make sure your environment also contains the training dependencies used by the current model services, including PyTorch and the test runner you intend to use.

## Where To Start

- general contribution flow: [CONTRIBUTING.md](CONTRIBUTING.md)
- beginner and scoped issue list: [GOOD_FIRST_ISSUES.md](GOOD_FIRST_ISSUES.md)

