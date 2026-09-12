# Scoring & Auditing — Prior-Work References

> **Purpose:** literature backing for the median-scoring, commit-reveal, encrypted-test-data, and contribution-valuation mechanisms discussed in [`MECHANISM_DESIGN.md`](MECHANISM_DESIGN.md) §5–6 and [`whitepaper-summary.md`](whitepaper-summary.md). Written to support [`task_210726_6`](../tasks/task_210726_6.md) (scoring/auditing/rewards). All links are public (arXiv preprints + a public GitHub repo) — no HR-internal material is referenced here.

---

## 1. BlockFlow — Mugunthan, Rahman, Kagal (2020)

**[arXiv:2007.03856](https://arxiv.org/abs/2007.03856)** — "BlockFlow: An Accountable and Privacy-Preserving Solution for Federated Learning"

This is the direct origin of the white paper's median-scoring language and its 0.5-from-median deviation threshold.

**Contribution Scoring Procedure (Algorithm 1):**
```
for all client pairs {a,k}:  s[a,k] = eval_a(k)             # a scores k's model
for all clients k:           m[k]   = MEDIAN(s[*, k])       # median score per model
for all clients k:           m'[k]  = m[k] / max(m)         # scale to max 1.0
for all pairs {a,k}:         t[a,k] = |s[a,k] - m[k]|
                             t'[a,k] = max(0, (0.5 - t[a,k]) / (0.5 + t[a,k]))
for all clients a:           d[a]   = min(t'[a,*])          # worst evaluation a performed
for all clients a:           d'[a]  = d[a] / max(d)
for all clients k:           p[k]   = min(m'[k], d'[k])      # overall score
```
Overall score = `min(scaled median score of my model, scaled accuracy of my worst evaluation)`. BlockFlow hard-codes the deviation cutoff at 0.5 with an a-priori score of 0.5 — confirms the *mechanism* behind DIN's S3 threshold, but DIN correctly ships it as a settable parameter rather than copying the literal constant.

**Five-stage round protocol — precedent for commit-then-reveal auditor scoring:**
> train → retrieve → **evaluation commit** → **evaluation reveal** → compute score

BlockFlow's variant encrypts the *score itself* with a random key and later reveals the decryption key (rather than a `keccak256(score, vote, salt)` hash commitment). Both solve the same problem — preventing an evaluator from copying an earlier evaluator's score — but a hash-commitment avoids per-round symmetric-key management.

**Model/data encryption — precedent for per-validator encrypted test-data keys:** BlockFlow encrypts models with Elliptic-Curve Diffie-Hellman keys derived from the sender's and receiver's chain accounts before distributing via IPFS, rather than storing a separately-encrypted key blob on-chain per recipient.

**Threat model:** guarantees hold for `M < N/2` malicious agents — the same bound the DIN validator set assumes elsewhere.

---

## 2. 2CP — Cai, Rueckert, Passerat-Palmbach (2020)

**[arXiv:2011.07516](https://arxiv.org/abs/2011.07516)** — "2CP: Decentralized Protocols to Transparently Evaluate Contributivity in Blockchain Federated Learning Environments"

The white paper's other scoring benchmark alongside BlockFlow (§5).

**Step-by-step marginal-gain contributivity:**
```
C(A) = Σ_i [ v(M_i) − v(M_i+1^A) ]
```
Contributivity of client A = sum, over training iterations, of the performance drop attributable to removing A's update at that step. Cites this as the only one of several Substra-explored contributivity measures usable in a *live* FL setting (as opposed to a post-hoc recomputation over the full history). This is the formal shape of the "marginal-gain gate" referenced in task_210726_6 §1b.

**GitHub dependency:** cites `github.com/SubstraFoundation/distributed-learning-contributivity` — now renamed **[LabeliaLabs/distributed-learning-contributivity](https://github.com/LabeliaLabs/distributed-learning-contributivity)**. Same repo the white paper cites directly as ref [34].

---

## 3. Shapley-value data valuation — Jia et al.

- **[arXiv:1902.10275](https://arxiv.org/abs/1902.10275)** — "Towards Efficient Data Valuation Based on the Shapley Value" (general Monte Carlo / truncated-MC estimators, `O(N(log N)^2)` model evaluations instead of exponential)
- **[arXiv:1908.08619](https://arxiv.org/abs/1908.08619)** — "Efficient Task-Specific Data Valuation for Nearest Neighbor Algorithms" (closed-form Shapley value for unweighted/weighted KNN utility functions, `O(N log N)`)

Cited in the white paper as alternative "objective scores" alongside median scoring. Both approximate the same underlying idea: draw a random ordering of contributors, add them one at a time, record each one's marginal utility gain in that ordering, average over many random orderings — exactly the "permutation averaging" + "sequential fold-in" language in `MECHANISM_DESIGN.md` §6 / issue #39.

**A runnable reference implementation exists** in `LabeliaLabs/distributed-learning-contributivity` (`mplc/contributivity.py`, method `truncated_MC`):
```python
permutation = np.random.permutation(n)
for j in range(n):
    contributions[-1][permutation[j]] = char_partnerlists[j+1] - char_partnerlists[j]
sv = np.mean(contributions, axis=0)   # average across permutations
```
The inner loop is "sequential fold-in" (adding partners one at a time, measuring the marginal delta); the outer average across random permutations is "permutation averaging." Useful as a concrete reference if `cache_model_0/services/scoring.py`/`aggregator.py` turn out not to implement either term (task_210726_6 §1a). The same file has 8 other contributivity-scoring variants (importance sampling, stratified sampling, Kriging-adaptive sampling) if a cheaper approximation is ever wanted.

**Important — do not resurface as a live option for per-datapoint valuation:** [`rejected-ideas/tknn-shapley.md`](../rejected-ideas/tknn-shapley.md) already rejected the Threshold-KNN-Shapley variant of this exact line of work (same KNN-Shapley family as arXiv:1908.08619 above) for *client/data-point* valuation, because it requires the auditor to see raw training features/labels — which FL's privacy model never exposes. The permutation-MC technique above is only reusable for DIN in its *model/update*-level form (scoring submitted parameter updates, à la `leave_one_out`/`marginal_global_delta`), not for scoring raw client data directly.

---

## 4. IPFS — Benet (2014)

**[arXiv:1407.3561](https://arxiv.org/abs/1407.3561)** — "IPFS - Content Addressed, Versioned, P2P File System"

Cited by the white paper alongside BlockFlow because BlockFlow's model-sharing guarantee depends on IPFS's content-addressing (objects addressed by the cryptographic hash of their contents → automatic tamper detection). Relevant to task_210726_6 §2b: the encrypted test-data is content-addressed and pinned the same way model artifacts already are elsewhere in `dincli`'s IPFS abstraction — no new infra pattern needed, just the on-chain key-mapping addition the task describes.

---

## Mapping to task_210726_6 deliverables

| Task item | Paper precedent |
|---|---|
| §1a spec-to-code mapping (fold-in / permutation averaging) | `mplc/contributivity.py:truncated_MC` — working reference if not found in `cache_model_0` |
| §1b marginal-gain gate | 2CP Eq. 1 (step-by-step contributivity) |
| §1c on-chain median as canonical score | BlockFlow Algorithm 1 (`MED{s[a,k]}`) |
| §1d S3 deviation threshold (shadow mode, settable) | BlockFlow's hard-coded 0.5-from-median confirms the mechanism; DIN correctly avoids hard-coding the number |
| §2a commit-then-reveal | BlockFlow's evaluation-commit/evaluation-reveal stage (encrypt-then-reveal-key variant; hash-commit as specified is a cleaner alternative) |
| §2b encrypted per-validator test-data key | BlockFlow's ECDH model encryption + IPFS content-addressing for the underlying data |
| §2c resampling policy | No paper precedent found — genuinely novel design work |
