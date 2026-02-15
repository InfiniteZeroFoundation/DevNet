import torch.nn as nn
import torch.nn.functional as F


class ModelArchitecture(nn.Module):
    def __init__(self):
        super(ModelArchitecture, self).__init__()
        self.fc1 = nn.Linear(28*28, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc3 = nn.Linear(64, 10)

    def forward(self, x):
        # x shape: [batch_size, 1, 28, 28]
        x = x.view(x.size(0), -1)         # flatten to [batch_size, 784]
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return x
