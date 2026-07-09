# Indexer

## Summary

This issue covers how DIN should use an indexer layer such as The Graph for scalable query answering instead of pushing complex enumeration and pagination logic into on-chain contracts wherever that can be avoided.

The core principle is:

- on-chain contracts should remain the canonical coordination and settlement layer
- indexers should handle rich querying, filtering, sorting, pagination, and historical views

This matters especially for DIN because protocol usage can eventually involve:

- many model registration requests
- many manifest update requests
- many validator stake and slash events
- many task deployments
- many governance actions

If contracts try to serve all of those read patterns directly on-chain, the design can become:

- storage-heavy
- gas-inefficient
- harder to audit
- harder to upgrade
- still poor at large-scale querying

## Why This Matters

Some queries are natural on-chain queries.

Examples:

- get model by id
- get stake for validator
- check whether a slasher is authorized
- check whether a model is disabled

Those are bounded, direct, and cheap.

Other queries are fundamentally better handled off-chain.

Examples:

- list all pending model requests
- paginate pending manifest updates
- show all models registered by one owner
- show historical fee changes
- show validator blacklist and slash history
- filter requests by status, age, owner, or contract address
- build governance dashboards

Trying to serve these patterns directly from Solidity usually leads to:

- unbounded arrays
- queue bookkeeping
- duplicated state
- extra storage writes
- complex pagination logic
- growing gas cost for writes just to support reads

That is usually the wrong tradeoff.

## Architectural Direction

For production DIN architecture, the better default is:

### On-chain

Use contracts for:

- canonical state
- authorization
- approvals and rejections
- slashing and staking
- ownership and governance execution
- immutable or auditable state transitions
- event emission

### Off-chain indexer

Use The Graph or a DIN-operated indexer for:

- filtering
- ordering
- pagination
- dashboards
- analytics
- activity feeds
- pending queues
- historical scans
- joins across contracts

This is how most mature protocols scale their read layer.

## Example: Registry Queries

`DINModelRegistry` is a good example of where indexer-first design makes sense.

The contract should remain responsible for:

- storing request state
- enforcing approval and rejection rules
- storing approved model metadata
- emitting request and state-transition events

The indexer should handle queries such as:

- all pending model requests
- all pending manifest requests
- requests by requester
- requests by task coordinator
- requests by task auditor
- requests created in a date range
- models grouped by open-source versus proprietary
- fee history timeline

These are read-layer concerns, not core settlement concerns.

## Example: Staking Queries

`DinValidatorStake` should remain responsible for:

- stake balances
- validator status
- pending withdrawals
- slash execution
- blacklist state

The indexer should handle queries such as:

- all active validators
- all exiting validators
- all blacklisted validators
- slash history by validator
- slash history by slasher contract
- total slashed over time
- validator activity timeline

Again, this is much better handled off-chain than by forcing enumerable on-chain structures.

## Example: Governance Queries

If DIN moves toward decentralized governance, the same principle applies.

Contracts should handle:

- proposal creation
- voting
- quorum
- execution
- timelock

The indexer should handle:

- proposal lists
- proposal filtering by type and status
- voter histories
- execution timelines
- treasury action history
- governance analytics

## What Not To Optimize On-Chain Prematurely

Where possible, DIN should avoid adding contract complexity whose main purpose is better querying.

That includes avoiding patterns like:

- giant arrays returned from view functions
- complex enumerable pending queues only for UI convenience
- duplicated status fields plus auxiliary pending arrays
- expensive swap-and-pop bookkeeping just to support listing
- state duplication that can drift out of sync

This does not mean no on-chain indexing aids are ever justified. It means the burden of proof should be high.

## Recommended Contract Design Principle

A good default rule is:

- if a data structure is required for correctness or execution, keep it on-chain
- if a data structure exists mainly to answer rich read queries, prefer the indexer

That is an important distinction.

For example:

- authorization mappings are execution-critical
- pending-request dashboards are not execution-critical

## Events First

If DIN wants a strong indexer layer, contracts should be designed with event quality in mind.

That means:

- every meaningful state transition should emit an event
- event payloads should include enough context for reconstruction
- key identifiers should be indexed where useful
- event naming should be stable and descriptive

Examples of useful indexed data:

- `requestId`
- `modelId`
- requester or owner address
- validator address
- slasher address
- contract address references

The contract can stay simple if the event layer is good.

## Pagination Strategy

Pagination should primarily be an indexer concern.

For large collections, the recommended query path is:

- index events and canonical state
- paginate in the indexer or query API
- return bounded result windows to clients

This is usually better than forcing Solidity to implement rich paging over large dynamic collections.

Where on-chain pagination is still useful, it should be:

- bounded
- simple
- secondary to the indexer path

It should not be the main product query strategy.

## Pending Request Views

A common temptation is to add explicit on-chain pending queues for requests.

That can be justified if queue membership or queue order is required for execution semantics.

But if the real goal is:

- admin review dashboards
- DAO reviewer workflow
- chronological browsing
- request filtering

then the indexer is usually the better place to build that view.

In many cases, pending state can be reconstructed from:

- request creation events
- approval events
- rejection events
- canonical request status in storage

without adding complex on-chain queue structures.

## Why This Is Better For DIN

DIN’s roadmap already points toward:

- decentralized model onboarding
- validator subnetworks
- many tasks and iterations
- richer governance
- growing operational data

That means query volume and query complexity will likely grow faster than settlement complexity.

If DIN keeps pushing read convenience into contracts, the protocol may end up paying permanent gas and complexity costs for a problem that indexers solve better.

An indexer-first architecture keeps:

- writes cheaper
- contracts cleaner
- audits easier
- upgrades easier
- product queries more flexible

## Minimal Solidity Changes Only Where Needed

This issue intentionally prefers indexer architecture over broad Solidity refactors where possible.

Good minimal contract changes, if needed, include:

- adding missing events for important transitions
- improving indexed event fields
- exposing direct point-lookups and counts
- using explicit status enums where that improves clarity

Less attractive changes include:

- building large enumerable storage for read convenience alone
- returning full arrays of live objects
- adding heavy queue structures if the indexer can answer the same product need

## What Should Stay On-Chain

DIN should still keep certain reads easy on-chain because they are used by contracts or critical clients.

Examples:

- current status of a request
- current validator stake and status
- whether a model is disabled
- current fee values
- whether a slasher is authorized

These are canonical, bounded, and important for execution.

## What Should Move To The Indexer

The indexer should be the default query layer for:

- paginated request lists
- pending review dashboards
- status-filtered request feeds
- historical analytics
- owner- or validator-specific timelines
- event history across multiple contracts
- cross-contract joins
- governance dashboards
- monitoring and alerting feeds

## The Real Production Pattern

The scalable production pattern for DIN is:

### Contract layer

- minimal canonical state
- execution logic
- events

### Indexer layer

- query API
- pagination
- filtering
- sorting
- historical aggregation
- UI-facing data models

### Client layer

- dashboards
- reviewer workflows
- governance views
- monitoring tools

This separation is cleaner than trying to make the Solidity layer act like an application database.

## Suggested Scope

Contributors working on indexing should focus on:

- identifying which DIN queries are best served by an indexer
- defining event coverage needed for those queries
- designing indexer entities and relations
- building paginated APIs or subgraph queries
- keeping contract changes minimal unless they improve canonical state or event quality

## Open Questions

- Which DIN product queries truly require on-chain enumerable structures, if any?
- Should DIN use The Graph directly, or maintain a DIN-operated indexer service with similar behavior?
- Are there any platform-level queues whose ordering is execution-critical rather than UI-critical?
- Which current events are insufficient for reconstructing state cleanly in an indexer?
- Should governance, registry, and staking data be indexed in one subgraph or separate modules?

## Good Contribution Directions

- define an indexer-first query architecture for registry, staking, and governance
- audit current contract events for indexer completeness
- propose missing events instead of broad storage-heavy query features
- build a subgraph or indexer schema for core DIN contracts
- document pagination and filtering requirements for DIN dashboards
- identify where on-chain query helpers are still justified and where they are not

## Conclusion

DIN should avoid turning Solidity contracts into heavy query engines where possible.

The better production design is:

- keep on-chain state minimal and canonical
- emit strong events
- use The Graph or a similar indexer for pagination, filtering, and historical queries

If a query pattern mainly serves dashboards, reviewers, governance interfaces, or analytics, it is usually a strong candidate for the indexer rather than additional on-chain enumeration logic.
