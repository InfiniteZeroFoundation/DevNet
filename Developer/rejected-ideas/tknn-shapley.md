# Rejected Idea: TKNN-Shapley for Client/Data Scoring in Federated Learning

## Summary

`TKNN-Shapley` (Threshold-KNN Shapley) was initially considered as a contribution-scoring and data-valuation backend for client reward weighting and data-quality diagnostics. However, a fundamental conflict exists between the design assumptions of TKNN-Shapley and the privacy requirements of Federated Learning (FL). 

In an FL protocol, the auditor/validator does not have access to clients' raw training data. Since TKNN-Shapley is designed to quantify the usefulness of individual data points and requires direct access to the training dataset, it is impossible to run in this decentralized setting.

Therefore, **TKNN-Shapley is rejected** as a scoring, validation, or reward mechanism for client submissions.

---

## Technical Mismatch: FL Requirements vs. TKNN Design

The core issue lies in the mismatch between what TKNN-Shapley assumes is available and what a privacy-preserving Federated Learning protocol actually exposes.

### TKNN Design Assumption (Centralized Setting)

In the standard centralized setting where TKNN is defined, a centralized validator/auditor has full access to the training and validation sets.

**The Auditor HAS:**
- $\checkmark$ $x_{train}$ (training features)
- $\checkmark$ $y_{train}$ (training labels)
- $\checkmark$ $x_{val}$ (validation features)
- $\checkmark$ $y_{val}$ (validation labels)

**The Auditor CAN:**
- $\checkmark$ Compute pairwise distances between all validation points and all training points.
- $\checkmark$ Apply the threshold $\tau$ to determine active training points for each validation point.
- $\checkmark$ Calculate Shapley values for individual training points based on their marginal contributions to the Threshold-KNN utility.
- $\checkmark$ Rank training samples by quality and detect mislabeled data.

> [!NOTE]
> Under these centralized assumptions, TKNN-Shapley works perfectly and is highly effective at data cleaning and data valuation.

---

### FL Privacy Requirement (Decentralized Setting)

In Federated Learning, client data privacy is a first-class citizen. Clients do not share their raw training features ($x_{train}$) or labels ($y_{train}$) with the server, auditor, or other clients. They only share their local model parameters or parameter updates.

**The Auditor DOES NOT have:**
- $\times$ $x_{train}$ (client training features are private)
- $\times$ $y_{train}$ (client training labels are private)

**The Auditor HAS:**
- $\checkmark$ $x_{val}$ (public validation features)
- $\checkmark$ $y_{val}$ (public validation labels)
- $\checkmark$ The client's local model parameters/updates

**The Auditor CANNOT:**
- $\times$ Compute distances (no access to $x_{train}$)
- $\times$ Apply threshold $\tau$ (no distances)
- $\times$ Calculate Shapley values for training points (no features or labels)
- $\times$ Rank training samples by quality (no per-sample visibility)
- $\times$ Detect mislabeled data (no raw data access)

> [!WARNING]
> Because the validator/auditor lacks access to the raw training datasets of each client, **TKNN-Shapley cannot execute** in the FL setting.

---

## Conceptual Mismatch: Data vs. Model Scoring

Beyond the privacy barriers, there is a conceptual mismatch in the target of valuation:

1. **TKNN-Shapley** is designed to quantify the usefulness of **individual training data samples** ($z_i = (x_i, y_i)$), not local models themselves.
2. In the DIN scoring plane, we need to evaluate the **local models** or **parameter updates** submitted by clients, or the marginal contribution of each client's aggregate update to the global model.
3. Attempting to run TKNN-Shapley on the validation set itself or treating validation points as the "training" set does not yield client contribution values for their actual local datasets.

---

## Alternatives for Contribution Scoring

To satisfy FL privacy constraints while still achieving fair reward weighting and contribution estimation, DIN will use alternative backends that operate directly on model updates or aggregate models:

1. **`leave_one_out` (LOO)**: Estimates client contribution by comparing the utility of the global model aggregated *with* the client's update against the global model aggregated *without* that client's update. This relies only on validation data and the model updates, which the auditor already possesses.
2. **`marginal_global_delta`**: Measures how much the client update improves the global model relative to a baseline model.
3. **Screening and Anomaly Scoring**: Detects malformed models, peer deviation, and update norm bounds without requiring raw training data access.
