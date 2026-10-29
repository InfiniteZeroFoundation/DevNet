# Contributing to DevNet

InfiniteZero is an open experiment. The DevNet is live, assumptions are being tested in real conditions, and there's real work to do. If you want to help build a global AI commons, this is where it happens.

## Getting Started

```bash
# Fork the repo and checkout develop
git checkout develop

# Install dependencies and set up dincli in editable mode
pip install -e .

# See full setup guide
/Developer/DEVELOPMENT_SETUP.md
```

Create a feature branch, commit your changes, and open a pull request to `develop`.

Every PR is reviewed and merged by someone other than its author. [MAINTAINING.md](MAINTAINING.md) describes how review, merging, and issue/task closure work.

## A Note On The Developer Docs

The materials in `/Developer` are working design input, not fixed specifications. They represent current thinking, not final decisions.

**Where documents live:** `Documentation/` describes what exists in the code on `develop` (`public/` for network participants, `technical/` for people modifying the code); `Developer/` holds plans, designs, proposals, tasks, and process docs. Before adding a document, read "Where does a new document go?" in [README.md](README.md).

Good contributors challenge assumptions, question tradeoffs, and propose alternatives. If you see a better path, say so. The goal is the right architecture, not defending the existing one.

## Ways To Contribute

**Bug fixes**: see open issues  
**Smart contracts** (Solidity): new features, security improvements  
**Python tooling**: enhance `dincli` or validator tooling  
**Documentation**: expand guides, improve clarity  
**Testing**: improve coverage  
**Research**: DP integration, contribution scoring, validator economics

For issue-specific contributor packets, review questions, and curated reading lists, start with [GOOD_FIRST_ISSUES.md](GOOD_FIRST_ISSUES.md) and then open the detailed issue linked from there.

## Submitting PRs

- Reference related issues. Write `Closes #N` only if the PR completes everything issue N asks (it then closes automatically on merge); otherwise write `Part of #N`
- Clear description of what and why
- Add tests where applicable
- Keep commits focused
- **Changed a `foundry/src` contract's interface?** Regenerate the affected bundled ABIs in the same PR, after `forge build`:
  ```
  dincli system dump-abi --artifact foundry/out/<Contract>.sol/<Contract>.json --output dincli/abis --official
  ```
  `dincli/abis/*.json` is the only ABI dincli has for the platform contracts (`DinCoordinator`, `DinToken`, `DinValidatorStake`, `DINModelRegistry`, `DinFeeRouter`), and the fallback for `DINTaskCoordinator`/`DINTaskAuditor` when a model's manifest doesn't supply custom `task_contracts` artifacts. A stale bundle means dincli calls functions that no longer exist (`AttributeError`) or decodes events/structs against the wrong layout. No network or wallet needed to run it. See [issue #177](https://github.com/InfiniteZeroFoundation/DevNet/issues/177) for what drifting looks like when this is skipped.
- **Contract size budget.** Every deployable `foundry/src` contract must keep at least **1,024 B** of runtime headroom under EIP-170's 24,576 B. Initcode must stay under EIP-3860's 49,152 B. CI enforces both with `.github/scripts/contract_size_gate.py`, and warns when a contract's margin drops below **2,048 B**. Both thresholds are constants at the top of the script (issue #201). Check locally after `forge build`:
  ```
  cd foundry && python3 ../.github/scripts/contract_size_gate.py
  ```
  `foundry/anvil.sh` lifts the limit on the local chain, so a local deploy is not a size check. A PR that pushes a contract under the 1,024 B fail line needs a size reduction in the same PR. Don't split a contract without raising it with a maintainer first.
- **Integration suite.** A PR that changes `foundry/src/`, `foundry/script/`, `foundry/anvil.sh`, `hardhat/`, `dincli/` or `tests/dincli/` also runs CI's **Integration (full GI)** job: the `tests/dincli/` suite on Anvil, an offline Kubo and Docker, in isolated mode (issue #228). It is non-blocking for now and does not gate `CI OK`. When it fails, the run's `integration-logs` artifact has the pytest output and the compile, chain and IPFS logs. To reproduce it locally, see [CI integration job](../Documentation/technical/testing/dincli-testing-guide.md#ci-integration-job).

## Code Standards

Python: PEP 8  
Solidity: community standards, nat-spec comments throughout
