# 🔹 GLOBAL

```
dincli --help
dincli --version
dincli --network >> <network|local|sepolia|mainnet>
```


# 🔹 SYSTEM UTILITIES

```
dincli system connect-wallet <0xprivatekey>
dincli system reset-all
dincli system reset <DINTaskCoordinatorAddress>
dincli system --usdt-info
dincli system din-info --coordinator|--token|--stake|--representative --network <net>
```


Datasets:
```
dincli system dataset distribute-mnist --clients <num>
```


# 🔹 DAO LAYER (PLATFORM LEVEL — DINCoordinator)

Everything here uses **DINCoordinator** only.

### Deploy platform contracts

```
dincli dindao deploy din-coordinator --network <net>

dincli dindao deploy din-token \
  --dinCoordinator <address> \
  --network <net>

dincli dindao deploy din-stake \
  --dinCoordinator <address> \
  --dinToken <address> \
  --network <net>
```

### Add platform-level slashers

```
dincli dindao add-slasher \
  --contract <address> \
  --network <net>
```

*(This slasher affects Aggregators & Auditors **via** TaskContract delegation; but lives at DAO level)*

---

# 🔹 MODEL OWNER COMMANDS

These create & operate **task-level** contracts.

---

## ▶️ 1. Buy USDT for task operations


```
dincli modelowner buy-usdt <amount> --network <net>
```

---


## ▶️ 2. Deploy Task-Level Contracts

### Deploy DINTaskCoordinator (task contract)

```
dincli modelowner deploy task-coordinator \
  --network <net> 
```

### Deploy DINTaskAuditor

```
dincli modelowner deploy task-auditor \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>
```

---

## ▶️ 3. Deposit USDT into DINTaskAuditor

```
dincli modelowner deposit-usdt \
  --taskAuditor <taskAuditorAddress> \
  <amount> \
  --network <net>
```

---

## ▶️ 4. Task-Level Slasher 

### **1. Add slasher to DINTaskCoordinator**

Used for slashing **Aggregators**.

```
dincli modelowner add-slasher \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <network>
```
### **2. Add slasher to DINTaskCoordinator**

Used for slashing **Aggregators**.

```
dincli modelowner add-slasher \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <network>
```

---

## ▶️ 5. Upload Genesis Model (GM)

```
dincli modelowner model create-genesis <ipfs-hash> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>
```


## ▶️ 6. GLOBAL ITERATION (GI) lifecycle (task-level)

All GI state is inside **DINTaskCoordinator**.

```
dincli modelowner gi start <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>

dincli modelowner gi end <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>
```


---

## ▶️ 7. Registration Phases

These belong to **DINTaskCoordinator (aggregators)**
and **DINTaskAuditor (auditors)** separately.

### Aggregator registration (task-level)

```
dincli modelowner reg aggregators-open <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>

dincli modelowner reg aggregators-close <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>
```

### Auditor registration (task-level)

```
dincli modelowner reg auditors-open <GI> \
  --taskAuditor <taskAuditorAddress> \
  --network <net>

dincli modelowner reg auditors-close <GI> \
  --taskAuditor <taskAuditorAddress> \
  --network <net>
```

---

## ▶️ 8. LMS Submissions Phase (Auditor contract)

```
dincli modelowner lms open <GI> \
  --taskAuditor <taskAuditorAddress> \
  --network <net>

dincli modelowner lms show <GI> \
  --taskAuditor <taskAuditorAddress> \
  --network <net>

dincli modelowner lms close <GI> \
  --taskAuditor <taskAuditorAddress> \
  --network <net>
```

---


## ▶️ 9. Auditor Batch Management

```
dincli modelowner auditor-batch create <GI> \
  --taskAuditor <taskAuditorAddress> \
  --network <net>

dincli modelowner auditor-batch assign-testCID <GI>  <ipfs-hash> \
  --taskAuditor <taskAuditorAddress> \
  --batch <batchIndex> \
  --network <net>
```

---


## ▶️ 10. Evaluation Phase (Auditor contract)

```
dincli modelowner lms-evaluation start <GI> \
  --taskAuditor <taskAuditorAddress> \
  --network <net>

dincli modelowner lms-evaluation close <GI> \
  --taskAuditor <taskAuditorAddress> \
  --network <net>
```

---
## ▶️ 11. Aggregation (T1 + T2) (TaskCoordinator contract)

```
dincli modelowner aggregation create-T1nT2-batches <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>
```

### T1 phase

```
dincli modelowner aggregation T1 start <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>

dincli modelowner aggregation T1 fnalize <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>
```

### T2 phase

```
dincli modelowner aggregation T2 start <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>

dincli modelowner aggregation T2 finalize <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>
```

---
## ▶️ 12. Slashing (TaskCoordinator contract)

```
dincli modelowner slash auditors <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>

dincli modelowner slash aggregators <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>
```

---


# 🔹 AGGREGATOR COMMANDS

Aggregator always interacts with **DINCoordinator (stake+token)** + **TaskCoordinator (task)**.

### Tokens & staking (DAO)

```
dincli aggregator buy DINtokens <amount> --network <net>
dincli aggregator stake DINtokens <amount> --network <net>
```

### Registration (task-level)

```
dincli aggregator register <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>
```

### T1 Batches

```
dincli aggregator getbatch T1 <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>

dincli aggregator submit T1 <ipfsHash> <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --scheme <aggregationScheme> \
  --network <net>
```

### T2 Batches

```
dincli aggregator getbatch T2 <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>

dincli aggregator submit T2 <ipfsHash> <GI> \
  --taskCoordinator <taskCoordinatorAddress> \
  --scheme <aggregationScheme> \
  --network <net>
```

---

# 🔹 AUDITOR COMMANDS

Auditors interact with **DINCoordinator (stake)** + **DINTaskAuditor (task)**.

### Token ops

```
dincli auditor buy DINtokens <amount> --network <net>
dincli auditor stake DINtokens <amount> --network <net>
```

### Registration (task auditor)

```
dincli auditor register \
  --taskAuditor <taskAuditorAddress> \
  --network <net>
```

### Get LMS for evaluation

```
dincli auditor getbatch <GI> \
  --taskAuditor <taskAuditorAddress> \
  --network <net>
```

### Evaluate

```
dincli auditor evaluate \
  --client <clientAddress> \
  --scheme <auditingScheme> \
  --taskAuditor <taskAuditorAddress> \
  --network <net>
```

---

# 🔹 CLIENT COMMANDS

Client interacts only with **TaskCoordinator** and their local training environment.

### Download initial model, latest model, and training scheme

```
dincli client download gm-initial \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>

dincli client download gm-latest \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>

dincli client download scheme \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>
```

### Create LMS

```
dincli client create-LMS \
  --initial <gm-initial.pkl> \
  --latest <gm-latest.pkl> \
  --scheme <training-scheme.pkl>
```

### Upload LMS (to TaskCoordinator)

```
dincli client upload-LMS <lmsFilePath> \
  --taskCoordinator <taskCoordinatorAddress> \
  --network <net>
```

---

















