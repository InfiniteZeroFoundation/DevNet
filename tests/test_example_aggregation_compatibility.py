"""Exercise example services in fresh processes to isolate sibling model imports."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("service", ["cache_model_0", "cache_model_1"])
@pytest.mark.parametrize("class_module", ["model", "aggregator"])
def test_serialized_model_and_aggregation(tmp_path, service, class_module):
    service_dir = Path(__file__).resolve().parents[1] / service / "services"
    # The aggregator-qualified case is constructed compatibility coverage, not
    # a claim about which module paths existing deployed artifacts contain.
    script = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import torch
import model
import aggregator
assert aggregator.ModelArchitecture is model.ModelArchitecture
model.ModelArchitecture.__module__ = sys.argv[3]
root = Path(sys.argv[2])
base = model.ModelArchitecture()
torch.save(base, root / 'genesis.pt')
loaded = torch.load(root / 'genesis.pt', weights_only=False)
assert isinstance(loaded, model.ModelArchitecture)
paths = []
for i, value in enumerate([2.0, 4.0]):
    state = {key: torch.full_like(tensor, value) for key, tensor in base.state_dict().items()}
    path = root / f'local-{i}.pt'
    torch.save(state, path)
    paths.append(path)
result = aggregator._average_state_dicts(paths, root / 'genesis.pt', root)
state = torch.load(result, weights_only=True)
assert state.keys() == base.state_dict().keys()
for value in state.values():
    torch.testing.assert_close(value, torch.full_like(value, 3.0))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(service_dir), str(tmp_path), class_module],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
