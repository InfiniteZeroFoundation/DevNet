# Developer

Forward-looking material for people building the DIN Protocol: plans, designs, proposals, contributor process, and work tracking.

> **Scope rule:** documents here describe **what we plan, propose, decide, or how we work** — they stay valid even as the code changes. Documentation of what currently exists on `develop` lives in [`Documentation/`](../Documentation/README.md) instead (`public/` for participants, `technical/` for people modifying the code).

## Layout

| Location | Contents |
|---|---|
| [ROADMAP.md](ROADMAP.md) | Active phase plans (P3–P4) and the full work-package table with owners, dependencies, and status |
| [UP_LOG.md](UP_LOG.md) | Completed phases moved out of ROADMAP.md once fully shipped (currently: P2) |
| [BACK_LOG.md](BACK_LOG.md) | Unscheduled / not-yet-phased items awaiting triage into a ROADMAP.md work package |
| [`design/`](design/) | Target designs not yet (fully) implemented: [system architecture](design/din-architecture.md), [DevNet 2.0 mechanism design](design/MECHANISM_DESIGN.md), [P3 design plan](design/p3-design-plan.md) (coordination page for the P3 mechanism-design push), [tokenomics design](design/tokenomics-design.md), [staking design](design/staking-design.md), [white paper summary](design/whitepaper-summary.md), [production staking/slashing spec](design/suggested-staking-mechanism.md), [feasibility report](design/feasibility-report.md), [design decisions log](design/DESIGN_DECISIONS.md) (cross-cutting decision tracker, started with DIN-DAO) |
| [`issues/`](issues/) | Backlog of design/implementation write-ups per mechanism or feature (some with `design.md` / `implementation.md` / `simulation.md` subdocs) |
| [`proposals/`](proposals/) | Tooling proposals — tools that don't exist yet (client labeling, model-owner contract/service builders) |
| [`tasks/`](tasks/) | Contributor task specs (`task_DDMMYY_n.md`) |
| [`discussion/`](discussion/) | Open discussions (Filecoin support, Foundry migration) |
| [`rejected-ideas/`](rejected-ideas/) | Ideas evaluated and rejected, with rationale (e.g. TKNN-Shapley) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution process and code standards pointers |
| [CODE_STANDARDS.md](CODE_STANDARDS.md) | Code style and quality expectations |
| [DEVELOPMENT_SETUP.md](DEVELOPMENT_SETUP.md) | Setting up a development environment |
| [GOOD_FIRST_ISSUES.md](GOOD_FIRST_ISSUES.md) | Curated starter tasks for new contributors |

## Where does a new document go?

1. **Describes code that exists on `develop`?** → `Documentation/` (never here). Participant-facing → `Documentation/public/`; for code readers/auditors → `Documentation/technical/`.
2. **A design or spec for something not built yet?** → `design/` (protocol mechanisms) or `proposals/` (tooling).
3. **A backlog item someone could pick up?** → `issues/`.
4. **A scoped task for a specific contributor?** → `tasks/`.
5. **An open question or debate?** → `discussion/`. A decision *not* to do something → `rejected-ideas/`.

**Graduation rule:** when a design from `design/` or `issues/` ships, don't move the document — write (or update) the current-state description in `Documentation/technical/` and mark the design here as shipped with a pointer. The design doc remains as the record of intent; `Documentation/` records reality. (Example: `issues/staking-mechanism.md` → `Documentation/technical/mechanisms/staking-mechanism.md`.)
