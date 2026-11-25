import torch
from torch.utils.data import DataLoader

from cache_model_1.prepare_training_data import save_client_partitions


def test_saved_partitions_contain_only_the_accounts_samples(tmp_path, capsys):
    samples = [(torch.tensor([[i]]), i) for i in range(10)]
    accounts = ["0xCarol", "0xAlice", "0xBob"]
    groups = [[0, 1, 2], [3, 4, 5], [6, 7, 8, 9]]

    save_client_partitions(samples, accounts, tmp_path)

    assert capsys.readouterr().out.splitlines() == [
        f"  [1/3] 3 samples → {tmp_path / '0xCarol' / 'data.pt'}",
        f"  [2/3] 3 samples → {tmp_path / '0xAlice' / 'data.pt'}",
        f"  [3/3] 4 samples → {tmp_path / '0xBob' / 'data.pt'}",
    ]
    for account, labels in zip(accounts, groups, strict=True):
        saved = torch.load(tmp_path / account / "data.pt", weights_only=False)
        assert isinstance(saved, list)
        assert not hasattr(saved, "dataset")
        expected = [(i, i) for i in labels]
        assert [(image.item(), label) for image, label in saved] == expected

        observed = []
        for images, batch_labels in DataLoader(saved, batch_size=2, shuffle=True):
            observed.extend(zip(images.flatten().tolist(), batch_labels.tolist(), strict=True))
        assert sorted(observed) == expected
