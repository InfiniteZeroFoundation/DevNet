"""tests/dincli/seed.py: seeding the isolated IPFS node with the reference
model's default artifacts (no IPFS node needed: `add` is faked)."""
import json

from tests.dincli import seed


def _fake_add(log):
    def add(path):
        assert path.is_file(), f"seed references a missing file: {path}"
        log.append(path)
        if path.is_relative_to(seed.DEVNET_ROOT):
            return "cid:" + path.relative_to(seed.DEVNET_ROOT).as_posix()
        return "cid:generated/" + path.name
    return add


def test_manifest_artifacts_point_at_repo_files():
    added = []
    manifest = seed.build_seeded_manifest(_fake_add(added))

    assert manifest["getGenesisModelIpfs"]["ipfs"] == "cid:cache_model_0/services/modelowner.py"
    assert manifest["Score_model_by_auditor"]["ipfs"] == "cid:cache_model_0/services/auditor.py"
    assert manifest["task_contracts"]["DINTaskCoordinator_Contract"]["artifact"]["ipfs"] == "cid:dincli/abis/DINTaskCoordinator.json"
    assert manifest["requirements.txt"]["auditors"] == "cid:cache_model_0/requirements/auditors/requirements.txt"
    # source / compilation entries carry no CID and stay untouched
    assert manifest["task_contracts"]["DINTaskAuditor_Contract"]["source"]["ipfs"] is None


def test_seed_returns_every_default_key(tmp_path, monkeypatch):
    # cid_services entries are checked against their expected CIDs; echo them back.
    expected = {
        (seed.CID_SERVICES_DIR / e["path"].lstrip("/").removeprefix("services/")): e["ipfs"]
        for e in json.loads(seed.CID_SERVICES_JSON.read_text())["services"].values()
    }
    expected.update({
        (seed.CID_SERVICES_DIR / "requirements" / (e["path"].rsplit("/", 1)[1].rsplit(".", 1)[0] + ".txt")): e["requirements"]
        for e in json.loads(seed.CID_SERVICES_JSON.read_text())["services"].values()
    })
    plain = _fake_add([])
    overrides = seed.seed_default_artifacts(lambda p: expected.get(p) or plain(p), tmp_path)

    assert overrides["default_manifest"] == "cid:generated/seeded_default_manifest.json"
    assert set(overrides) == {"default_manifest", "default_services", "default_abis", "default_requirements", "default_test_dataset"}
    assert overrides["default_test_dataset"] == "cid:cache_model_0/dataset/test/test_dataset.pt"
    assert set(overrides["default_requirements"]) == {"clients", "auditors", "aggregators", "modelowner"}


def test_apply_din_info_overrides_merges(tmp_path):
    path = tmp_path / "din_info.json"
    path.write_text(json.dumps({"local": {"token": "0xT", "default_manifest": "old"}}))
    seed.apply_din_info_overrides(path, "local", {"default_manifest": "new"})
    assert json.loads(path.read_text())["local"] == {"token": "0xT", "default_manifest": "new"}
