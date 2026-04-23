This is the guide from Model Owner to Clients.

# Instructions for Clients

Hi Client, Welcome to the decentralized AI training platform! You are about to participate in a collaborative model training process where your data contributes to a shared global model while maintaining your privacy. Please read the following instructions carefully to understand your role and the steps involved. This guide will walk you through the entire process, from setting up your environment to contributing your data and participating in the training.

## Pre-requisites

- Ensure you have the `dincli` installed and configured on your system.
- The client local training data must be  located at `<CACHE_DIR>/sepolia_op_devnet/model_<model_id>/dataset/clients/<account_address>/data.pt` where `CACHE_DIR` is the path to the cache directory of the dincli. and can be found by running the command `dincli system cache-dir`.

## Dataset Format

### Overview

The client dataset must be saved as a `data.pt` file at the path described in the [Pre-requisites](#pre-requisites) section above. The file is loaded using `torch.load(path, weights_only=False)` and must be compatible with `torch.utils.data.DataLoader`.

### Expected Data Structure

The dataset should be a **list of `(input_tensor, label)` tuples**, where:

| Field | Type | Description |
|---|---|---|
| `input_tensor` | `torch.Tensor` | A single-channel image tensor of shape `(1, 28, 28)` |
| `label` | `int` | An integer class label in the range `0–9` |

**Example:**

```python
# Each element in the dataset list:
(tensor_of_shape_1x28x28, label_int)

# The full dataset loaded from data.pt:
dataset = [(img_tensor_0, 0), (img_tensor_1, 3), ...]
```

### Preprocessing

Before saving, input images must be preprocessed with the following transforms:

```python
from torchvision import transforms

transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.1307,), (0.3081,))
])
```

- `ToTensor()` converts the image to a `torch.FloatTensor` in the range `[0.0, 1.0]`.
- `Normalize((0.1307,), (0.3081,))` normalizes using the MNIST dataset mean and standard deviation.

### Training Hyperparameters

The following default hyperparameters are used during client-side local training:

| Parameter | Value |
|---|---|
| Batch Size | `32` |
| Local Epochs | `10` |
| Optimizer | `Adam` (lr=`0.001`) |
| Loss Function | `CrossEntropyLoss` |


