# Client-Side Data Labeling & The Labeling Paradox

## Summary

In Federated Learning (FL), raw data remains localized on client devices to preserve privacy. However, most practical FL workflows assume that this local data is already labeled and ready for supervised learning. 

In reality, raw data collected by edge devices (e.g., photos, sensor readings, ambient text, audio) is unlabeled. Labeling data locally is a significant bottleneck. This issue addresses the **Labeling Paradox in FL** and explores automatic, semi-supervised, and human-in-the-loop (HITL) techniques to make local client datasets compatible with FL optimization.

---

## The Labeling Paradox

The labeling paradox in Federated Learning can be stated as follows:

> [!CAUTION]
> **The Paradox:**
> - To train a high-quality generalized global model, we need high-quality labeled local datasets from clients.
> - To automatically label local datasets (e.g., via pseudo-labeling), we need a high-quality generalized global model to make accurate predictions.

If the protocol initializes with a poor global model:
1. The global model generates highly noisy pseudo-labels on unlabeled client data.
2. The clients train local models using these noisy pseudo-labels, reinforcing the model's own biases and errors.
3. Aggregation results in a degraded global model, entering a negative feedback loop.

---

## Core Techniques for Client-Side Labeling

To break the labeling paradox and enable local optimization on raw edge data, several techniques should be supported by the InfiniteZero client service architecture:

### 1. Semi-Supervised Federated Learning (SSFL)

SSFL splits the learning process between labeled data (often hosted centrally or on a few dedicated clients) and unlabeled data (on edge clients).

- **Consistency Regularization (e.g., FixMatch / MixMatch)**:
  - The client applies weak and strong augmentations to the same raw data point.
  - The local model predicts a label on the weakly augmented image. If confidence exceeds a threshold, this prediction becomes a "pseudo-label."
  - The model is then trained to predict the same pseudo-label on the strongly augmented image.
  - *FL Benefit:* Does not require a fully trained global model to start; the local model learns representations and labels concurrently.

- **Federated Pseudo-Labeling with Adaptive Thresholds**:
  - The global model provides initial predictions.
  - Clients filter predictions using dynamic confidence thresholds (e.g., higher thresholds for classes with high variance) to minimize pseudo-label noise.

### 2. Weak Supervision on the Edge

Rather than relying on deep learning models for labeling, clients can run lightweight, rule-based heuristics locally to programmatically label data.

- **Labeling Functions (LFs)**:
  - Define simple programmatic heuristics (e.g., "if text contains 'buy', label as transaction").
  - Run consensus models (like Snorkel) locally on the client to combine noisy LFs into a single probabilistic label.
- **Local Foundation Model Distillation**:
  - Use a small, quantized, local zero-shot model (e.g., a small vision-language model or local LLM) running on the edge device to assign initial labels to raw data points.

### 3. Active Learning & Human-in-the-Loop (HITL)

When automatic methods fail, client users can be brought into the loop to label high-value data points. Because the data is local, the user can review and label it without leaking privacy.

- **Uncertainty Sampling**:
  - The local model identifies data points with the highest prediction entropy or lowest margin confidence.
  - The client UI prompts the user to label only these high-uncertainty samples.
- **Diversity Sampling**:
  - The client clusters raw data embeddings and asks the user to label representative samples from each cluster, maximizing label coverage with minimal human effort.

---

## Checking Data and Label Quality

Since the validator/auditor cannot inspect client training data ($x_{train}, y_{train}$), we need client-side telemetry to verify that labeling is not corrupting the training process.

### 1. Entropy and Confidence Monitoring
Clients should compute and report summary statistics of their local label confidence distributions (e.g., mean entropy of pseudo-labels, percentage of data points passing the confidence threshold).

### 2. Local Golden Validation Sets
Clients should maintain a small, human-verified "golden validation set" locally. This set is never used for training or pseudo-labeling. Instead, it is used to:
- Measure the accuracy of pseudo-labeling mechanisms.
- Report local generalization error to the client service logs.

### 3. Class Drift and Imbalance Detection
Monitor the distribution of labels generated locally. If a client's pseudo-labeler assigns 100% of samples to a single class, it indicates a collapsed pseudo-labeling state, and the update should be screened or throttled.

---

## Proposed Roadmap

### Phase 1: Client Semi-Supervised Baseline
- Implement PyTorch-based `FixMatch` or local consistency regularization helpers in `client.py`.
- Define configuration fields in `manifest.json` for confidence thresholds and augmentation types.

### Phase 2: Active Learning Hooks
- Create background daemon hooks in the client CLI to select high-entropy local samples.
- Define a standardized local API that a user-facing tagging UI can query to fetch unlabeled samples and post tags.

### Phase 3: Telemetry & Screening
- Add local validation metrics to the client execution report (e.g., pseudo-label validation accuracy on the local golden set).
- Update auditor screening logic to reject updates from clients experiencing pseudo-label collapse.
