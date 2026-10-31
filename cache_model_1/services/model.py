import torch.nn as nn
import torch.nn.functional as F


class ModelArchitecture(nn.Module):
    """Two-layer CNN for Fashion-MNIST classification.

    Input: [batch, 1, 28, 28]
    Conv1 → MaxPool → Conv2 → MaxPool → FC → Dropout → FC
    Output: logits over 10 clothing categories.
    """

    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.fc1 = nn.Linear(64 * 7 * 7, 256)
        self.fc2 = nn.Linear(256, 10)
        self.dropout = nn.Dropout(0.25)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))   # → [batch, 32, 14, 14]
        x = self.pool(F.relu(self.conv2(x)))   # → [batch, 64, 7, 7]
        x = x.view(x.size(0), -1)             # → [batch, 3136]
        x = F.relu(self.fc1(x))
        x = self.dropout(x)
        return self.fc2(x)
