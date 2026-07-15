import json
import os
import re
import stat
import tempfile
from getpass import getpass
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from rich.console import Console

import pytest
import typer
from eth_account import Account
from typer.testing import CliRunner

from dincli.cli import system as system_mod
from dincli.cli import utils as utils_mod
from dincli.main import app as main_app


DUMMY_KEY_0 = "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
DUMMY_KEY_1 = "0xfedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
DUMMY_PW = "test-password"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Strip ANSI color codes so assertions match rich-rendered CLI output."""
    return _ANSI_RE.sub("", text)

@pytest.fixture
def temp_config(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    wallets_dir = config_dir / "wallets"
    wallets_dir.mkdir()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    orig_config = utils_mod.CONFIG_DIR
    orig_cache = utils_mod.CACHE_DIR
    orig_wallets = utils_mod.WALLETS_DIR

    sys_orig_config = getattr(system_mod, "CONFIG_DIR", None)
    sys_orig_cache = getattr(system_mod, "CACHE_DIR", None)
    sys_orig_config_file = getattr(system_mod, "CONFIG_FILE", None)
    sys_orig_wallet_file = getattr(system_mod, "WALLET_FILE", None)
    sys_orig_worker_cache = getattr(system_mod, "WORKER_CACHE_DIR", None)

    utils_mod.CONFIG_DIR = config_dir
    utils_mod.CACHE_DIR = cache_dir
    utils_mod.WALLETS_DIR = wallets_dir
    utils_mod.WALLET_FILE = config_dir / "wallet.json"
    utils_mod.LEGACY_WALLET_FILE = config_dir / "wallet.json"

    if sys_orig_config is not None:
        system_mod.CONFIG_DIR = config_dir
    if sys_orig_cache is not None:
        system_mod.CACHE_DIR = cache_dir
    if sys_orig_config_file is not None:
        system_mod.CONFIG_FILE = config_dir / "config.json"
    if sys_orig_wallet_file is not None:
        system_mod.WALLET_FILE = config_dir / "wallet.json"
    if sys_orig_worker_cache is not None:
        system_mod.WORKER_CACHE_DIR = cache_dir / "worker"

    try:
        yield {
            "config_dir": config_dir,
            "wallets_dir": wallets_dir,
            "cache_dir": cache_dir,
        }
    finally:
        utils_mod.CONFIG_DIR = orig_config
        utils_mod.CACHE_DIR = orig_cache
        utils_mod.WALLETS_DIR = orig_wallets
        utils_mod.WALLET_FILE = orig_config / "wallet.json"
        utils_mod.LEGACY_WALLET_FILE = orig_config / "wallet.json"

        if sys_orig_config is not None:
            system_mod.CONFIG_DIR = sys_orig_config
        if sys_orig_cache is not None:
            system_mod.CACHE_DIR = sys_orig_cache
        if sys_orig_config_file is not None:
            system_mod.CONFIG_FILE = sys_orig_config_file
        if sys_orig_wallet_file is not None:
            system_mod.WALLET_FILE = sys_orig_wallet_file
        if sys_orig_worker_cache is not None:
            system_mod.WORKER_CACHE_DIR = sys_orig_worker_cache


class DummyConsole:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):
        self.messages.append(args)


class DummyCtxObj:
    def __init__(self, wallet_name=None, resolved_wallet_name="default"):
        self.console = Console()
        self.wallet_name = wallet_name
        self._resolved_wallet_name = resolved_wallet_name

    @property
    def resolved_wallet_name(self):
        return self._resolved_wallet_name

    @property
    def account(self):
        return SimpleNamespace(address="0xDead")

    def get_en_w3_account_console(self, model_id=None):
        return "local", None, SimpleNamespace(address="0xDead"), self.console


def make_ctx():
    return SimpleNamespace(obj=DummyCtxObj())


class TestUtilsFunctions:
    def test_validate_account_name_valid(self):
        assert utils_mod.validate_account_name("validator") == "validator"
        assert utils_mod.validate_account_name("my-wallet_01") == "my-wallet_01"
        assert utils_mod.validate_account_name("a") == "a"
        assert utils_mod.validate_account_name("A" * 64) == "A" * 64

    def test_validate_account_name_invalid(self):
        for bad in ["", "..", "../", "a/b", "wallet name", "a" * 65, "/etc/passwd"]:
            with pytest.raises(ValueError):
                utils_mod.validate_account_name(bad)

    def test_wallet_path_for_name(self):
        p = utils_mod.wallet_path_for_name("test")
        assert p.name == "wallet_test.json"

    def test_resolve_wallet_path_named_wins(self, temp_config):
        named = temp_config["wallets_dir"] / "wallet_default.json"
        legacy = temp_config["config_dir"] / "wallet.json"
        named.write_text('{"address": "0xNamed"}')
        legacy.write_text('{"address": "0xLegacy"}')
        path, exists = utils_mod.resolve_wallet_path("default")
        assert exists
        assert path == named

    def test_resolve_wallet_path_legacy_fallback(self, temp_config):
        legacy = temp_config["config_dir"] / "wallet.json"
        legacy.write_text('{"address": "0xLegacy"}')
        path, exists = utils_mod.resolve_wallet_path("default")
        assert exists
        assert path == legacy

    def test_resolve_wallet_path_not_found(self, temp_config):
        path, exists = utils_mod.resolve_wallet_path("nonexistent")
        assert not exists
        assert path.name == "wallet_nonexistent.json"

    def test_extract_keystore_wrapper(self):
        inner = Account.encrypt(DUMMY_KEY_0, DUMMY_PW)
        wrapper = {"version": 1, "address": "0xAbc", "keystore": inner, "source": "created"}
        result = utils_mod._extract_keystore(wrapper)
        assert "crypto" in result

    def test_extract_keystore_bare(self):
        inner = Account.encrypt(DUMMY_KEY_0, DUMMY_PW)
        result = utils_mod._extract_keystore(inner)
        assert "crypto" in result

    def test_extract_keystore_invalid(self):
        with pytest.raises(ValueError):
            utils_mod._extract_keystore({"not": "keystore"})

    def test_in_memory_password_cache(self, monkeypatch):
        utils_mod._PASSWORD_CACHE.clear()
        os.environ.pop("DIN_WALLET_PASSWORD", None)
        monkeypatch.setattr(utils_mod, "get_env_key", lambda key, verbose=None: None)
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: "cached-pw")

        p1 = utils_mod._get_password("test-acct")
        assert p1 == "cached-pw"

        utils_mod._cache_password_in_memory("test-acct", "cached-pw")
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: "should-not-be-called")
        p2 = utils_mod._get_password("test-acct")
        assert p2 == "cached-pw"

    def test_in_memory_password_cache_expires(self, monkeypatch):
        utils_mod._PASSWORD_CACHE.clear()
        monkeypatch.setattr(utils_mod, "get_env_key", lambda key, verbose=None: None)
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: "expired-pw")
        fake_time = [0.0]

        def fake_time_fn():
            return fake_time[0]

        monkeypatch.setattr(utils_mod.time, "time", fake_time_fn)

        p1 = utils_mod._get_password("test-acct")
        assert p1 == "expired-pw"

        fake_time[0] = _PASSWORD_TTL_DEFAULT + 1
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: "new-pw")
        p2 = utils_mod._get_password("test-acct")
        assert p2 == "new-pw"

    def test_clear_memory_cache(self, monkeypatch):
        utils_mod._PASSWORD_CACHE.clear()
        monkeypatch.setattr(utils_mod, "get_env_key", lambda key, verbose=None: None)
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: "pw")
        utils_mod._cache_password_in_memory("acct-a", "pw")
        utils_mod._cache_password_in_memory("acct-b", "pw")
        assert len(utils_mod._PASSWORD_CACHE) == 2

        assert utils_mod._clear_memory_cache("acct-a") is True
        assert len(utils_mod._PASSWORD_CACHE) == 1
        assert utils_mod._clear_memory_cache("acct-b") is True
        assert len(utils_mod._PASSWORD_CACHE) == 0

    def test_cleanup_stale_session_removes_file(self, temp_config):
        session = temp_config["config_dir"] / ".session"
        session.write_text("old-password")
        assert session.exists()
        utils_mod._cleanup_stale_session()
        assert not session.exists()

    def test_cleanup_stale_session_no_file(self, temp_config):
        session = temp_config["config_dir"] / ".session"
        assert not session.exists()
        utils_mod._cleanup_stale_session()

    def test_list_accounts_named(self, temp_config, monkeypatch):
        monkeypatch.setattr(utils_mod, "get_config", lambda key, default=None: default)
        acct0 = Account.create()
        acct1 = Account.create()
        w0 = {"version": 1, "address": acct0.address, "keystore": {}, "source": "created", "name": "alfa"}
        w1 = {"version": 1, "address": acct1.address, "keystore": {}, "source": "imported", "name": "beta"}
        (temp_config["wallets_dir"] / "wallet_alfa.json").write_text(json.dumps(w0))
        (temp_config["wallets_dir"] / "wallet_beta.json").write_text(json.dumps(w1))

        entries = utils_mod.list_accounts(active_name="alfa")
        assert len(entries) >= 2
        names = {e["name"] for e in entries}
        assert "alfa" in names
        assert "beta" in names
        alfa = next(e for e in entries if e["name"] == "alfa")
        assert alfa["active"] is True
        assert alfa["address"] == acct0.address

    def test_list_accounts_legacy_only(self, temp_config, monkeypatch):
        monkeypatch.setattr(utils_mod, "get_config", lambda key, default=None: default)
        acct = Account.create()
        legacy = temp_config["config_dir"] / "wallet.json"
        legacy.write_text(json.dumps({"address": acct.address, "crypto": {}}))

        entries = utils_mod.list_accounts(active_name="default")
        assert len(entries) == 1
        assert entries[0]["name"] == "default (legacy)"
        assert entries[0]["active"] is True

    def test_list_accounts_named_default_no_legacy_duplicate(self, temp_config, monkeypatch):
        monkeypatch.setattr(utils_mod, "get_config", lambda key, default=None: default)
        named = {"version": 1, "address": "0xNamed", "keystore": {}, "source": "created"}
        legacy = {"address": "0xLegacy", "crypto": {}}
        (temp_config["wallets_dir"] / "wallet_default.json").write_text(json.dumps(named))
        (temp_config["config_dir"] / "wallet.json").write_text(json.dumps(legacy))

        entries = utils_mod.list_accounts(active_name="default")
        names = {e["name"] for e in entries}
        assert "default" in names
        assert "default (legacy)" not in names


class TestAtomicWrite:
    def test_atomic_write_creates_file(self, temp_config):
        path = temp_config["wallets_dir"] / "wallet_test.json"
        data = {"version": 1, "address": "0xTest"}
        utils_mod.atomic_write_wallet(path, data)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded == data

    def test_atomic_write_permissions_0600(self, temp_config):
        path = temp_config["wallets_dir"] / "wallet_perm.json"
        utils_mod.atomic_write_wallet(path, {"test": True})
        st = path.stat()
        assert st.st_mode & 0o777 == 0o600

    def test_atomic_write_overwrites_loose_permissions(self, temp_config):
        path = temp_config["wallets_dir"] / "wallet_loose.json"
        path.write_text("{}")
        os.chmod(path, 0o644)
        utils_mod.atomic_write_wallet(path, {"test": True})
        st = path.stat()
        assert st.st_mode & 0o777 == 0o600

    def test_ensure_wallets_dir_permissions(self, temp_config):
        utils_mod.ensure_wallets_dir()
        st = temp_config["wallets_dir"].stat()
        assert st.st_mode & 0o777 == 0o700


class TestRegisterWalletKeystore:
    def test_keystore_import_valid(self, temp_config, monkeypatch):
        acct = Account.create()
        ks = Account.encrypt(acct.key.hex(), "import-pw")
        ks_path = temp_config["config_dir"] / "test.json"
        ks_path.write_text(json.dumps(ks))

        monkeypatch.setattr(system_mod, "get_config", lambda key, default=None: False)
        monkeypatch.setattr(system_mod, "load_config", lambda: {})
        monkeypatch.setattr(system_mod, "getpass", lambda prompt: "import-pw")

        ctx = make_ctx()
        connect_kwargs = {
            "ctx": ctx, "privatekey": None, "key_file": None,
            "account": None, "keystore": ks_path, "name": "validator",
        }
        system_mod.register_wallet(**connect_kwargs)

        saved = temp_config["wallets_dir"] / "wallet_validator.json"
        assert saved.exists()
        data = json.loads(saved.read_text())
        assert data.get("version") == 1
        assert data.get("name") == "validator"
        assert data.get("source") == "imported"
        assert "keystore" in data
        assert "crypto" in data["keystore"]

    def test_keystore_import_wrong_password(self, temp_config, monkeypatch):
        acct = Account.create()
        ks = Account.encrypt(acct.key.hex(), "real-pw")
        ks_path = temp_config["config_dir"] / "test.json"
        ks_path.write_text(json.dumps(ks))

        monkeypatch.setattr(system_mod, "get_config", lambda key, default=None: False)
        monkeypatch.setattr(system_mod, "load_config", lambda: {})
        monkeypatch.setattr(system_mod, "getpass", lambda prompt: "wrong-pw")

        ctx = make_ctx()
        connect_kwargs = {
            "ctx": ctx, "privatekey": None, "key_file": None,
            "account": None, "keystore": ks_path, "name": "bad",
        }
        with pytest.raises(typer.Exit):
            system_mod.register_wallet(**connect_kwargs)

        saved = temp_config["wallets_dir"] / "wallet_bad.json"
        assert not saved.exists()

    def test_keystore_import_missing_file(self, temp_config, monkeypatch):
        ctx = make_ctx()
        connect_kwargs = {
            "ctx": ctx, "privatekey": None, "key_file": None,
            "account": None, "keystore": Path("/nonexistent/ks.json"), "name": "nope",
        }
        with pytest.raises(typer.Exit):
            system_mod.register_wallet(**connect_kwargs)

    def test_keystore_import_malformed_json(self, temp_config, monkeypatch):
        ks_path = temp_config["config_dir"] / "bad.json"
        ks_path.write_text("not json")

        monkeypatch.setattr(system_mod, "get_config", lambda key, default=None: False)
        monkeypatch.setattr(system_mod, "load_config", lambda: {})

        ctx = make_ctx()
        connect_kwargs = {
            "ctx": ctx, "privatekey": None, "key_file": None,
            "account": None, "keystore": ks_path, "name": "bad",
        }
        with pytest.raises(typer.Exit):
            system_mod.register_wallet(**connect_kwargs)


class TestRegisterWalletMutualExclusivity:
    def test_two_methods_exits(self, monkeypatch):
        monkeypatch.setattr(system_mod, "get_config", lambda key, default=None: False)
        ctx = make_ctx()
        with pytest.raises(typer.Exit):
            system_mod.register_wallet(
                ctx=ctx, privatekey=DUMMY_KEY_0, key_file=None,
                account=None, keystore=Path("test.json"), name="default",
            )


class TestRegisterWalletNamedAccounts:
    def test_save_named_wrapper_schema(self, temp_config, monkeypatch):
        monkeypatch.setattr(system_mod, "get_config", lambda key, default=None: False)
        monkeypatch.setattr(system_mod, "load_config", lambda: {})
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: DUMMY_PW)
        monkeypatch.setattr(system_mod, "getpass", lambda prompt: DUMMY_PW)

        ctx = SimpleNamespace(obj=DummyCtxObj())
        system_mod.register_wallet(
            ctx=ctx, privatekey=DUMMY_KEY_0, key_file=None,
            account=None, keystore=None, name="prod",
        )

        saved = temp_config["wallets_dir"] / "wallet_prod.json"
        assert saved.exists()
        data = json.loads(saved.read_text())
        assert data.get("version") == 1
        assert data.get("source") == "created"
        assert data.get("name") == "prod"
        assert "keystore" in data

    def test_name_validation_rejects_bad(self, monkeypatch):
        monkeypatch.setattr(system_mod, "get_config", lambda key, default=None: False)
        ctx = make_ctx()
        for bad_name in ["../escape", "a/b", "wallet name", "a" * 100]:
            with pytest.raises((typer.Exit, ValueError)):
                system_mod.register_wallet(
                    ctx=ctx, privatekey=DUMMY_KEY_0, key_file=None,
                    account=None, keystore=None, name=bad_name,
                )


class TestReadWallet:
    def test_read_wallet_named_wallet(self, temp_config, monkeypatch):
        monkeypatch.setattr(utils_mod, "get_env_key", lambda key, verbose=None: None)
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: DUMMY_PW)
        monkeypatch.setattr(utils_mod, "_cleanup_stale_session", lambda: None)
        monkeypatch.setattr(utils_mod, "get_config", lambda key, default=None: None)

        ks = Account.encrypt(DUMMY_KEY_0, DUMMY_PW)
        wrapper = {"version": 1, "address": Account.from_key(DUMMY_KEY_0).address, "keystore": ks, "source": "created", "name": "default"}
        (temp_config["wallets_dir"] / "wallet_default.json").write_text(json.dumps(wrapper))

        ctx = SimpleNamespace(obj=DummyCtxObj())
        system_mod.read_wallet(ctx)


class TestTodoWalletAwareness:
    def test_todo_shows_named_wallet(self, temp_config, monkeypatch):
        monkeypatch.setattr(utils_mod, "get_env_key", lambda key, verbose=None: None)
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: DUMMY_PW)
        monkeypatch.setattr(utils_mod, "_cleanup_stale_session", lambda: None)
        monkeypatch.setattr(utils_mod, "get_config", lambda key, default=None: None)
        monkeypatch.setattr(system_mod, "resolve_ipfs_config", lambda: SimpleNamespace(provider="env", api_url_add="http://x", api_url_retrieve="http://y", api_key=None, api_secret=None, service_path=None))

        ks = Account.encrypt(DUMMY_KEY_0, DUMMY_PW)
        wrapper = {"version": 1, "address": Account.from_key(DUMMY_KEY_0).address, "keystore": ks, "source": "created", "name": "default"}
        (temp_config["wallets_dir"] / "wallet_default.json").write_text(json.dumps(wrapper))
        (temp_config["config_dir"] / "config.json").write_text('{"network": "local", "log_level": "info", "demo_mode": false}')

        ctx = SimpleNamespace(obj=DummyCtxObj())
        #ctx.obj.console.messages.clear()
        system_mod.todo(ctx)


class TestLoadAccount:
    def test_load_account_named_wallet(self, temp_config, monkeypatch):
        monkeypatch.setattr(utils_mod, "get_env_key", lambda key, verbose=None: None)
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: DUMMY_PW)
        monkeypatch.setattr(utils_mod, "_cleanup_stale_session", lambda: None)

        ks = Account.encrypt(DUMMY_KEY_0, DUMMY_PW)
        acct = Account.from_key(DUMMY_KEY_0)
        wrapper = {"version": 1, "address": acct.address, "keystore": ks, "source": "created", "name": "prod"}
        (temp_config["wallets_dir"] / "wallet_prod.json").write_text(json.dumps(wrapper))

        loaded = utils_mod.load_account(name="prod")
        assert loaded.address == acct.address

    def test_load_account_legacy_fallback(self, temp_config, monkeypatch):
        monkeypatch.setattr(utils_mod, "get_env_key", lambda key, verbose=None: None)
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: DUMMY_PW)
        monkeypatch.setattr(utils_mod, "_cleanup_stale_session", lambda: None)

        ks = Account.encrypt(DUMMY_KEY_0, DUMMY_PW)
        acct = Account.from_key(DUMMY_KEY_0)
        legacy = temp_config["config_dir"] / "wallet.json"
        legacy.write_text(json.dumps(ks))

        loaded = utils_mod.load_account(name="default")
        assert loaded.address == acct.address

    def test_load_account_demo_mode(self, temp_config, monkeypatch):
        monkeypatch.setattr(utils_mod, "_cleanup_stale_session", lambda: None)
        demo = {"demo_mode": True, "private_key": DUMMY_KEY_0, "address": Account.from_key(DUMMY_KEY_0).address}
        (temp_config["wallets_dir"] / "wallet_demo.json").write_text(json.dumps(demo))

        loaded = utils_mod.load_account(name="demo")
        assert loaded.address == Account.from_key(DUMMY_KEY_0).address


class TestCLICommands:
    def test_list_accounts_command_empty(self, monkeypatch, temp_config):
        monkeypatch.setattr(system_mod, "resolve_ipfs_config", lambda: SimpleNamespace(provider="env", api_url_add=None, api_url_retrieve=None, api_key=None, api_secret=None, service_path=None))
        result = CliRunner().invoke(
            main_app, ["system", "list-accounts"],
        )
        assert "No wallets found" in result.output or result.exit_code == 0

    def test_help_exposes_new_commands(self):
        result = CliRunner().invoke(main_app, ["system", "register-wallet", "--help"])
        plain = _plain(result.output)
        assert "--keystore" in plain
        assert "--name" in plain
        assert "--connect" in plain

    def test_connect_wallet_help_documents_priority(self):
        result = CliRunner().invoke(main_app, ["system", "connect-wallet", "--help"])
        assert result.exit_code == 0
        assert "DIN_WALLET_NAME" in _plain(result.output)


class TestFixARegression:
    def test_demo_mode_creates_wallets_dir(self, monkeypatch):
        bare = tempfile.mkdtemp()
        try:
            config_dir = Path(bare) / "config"
            config_dir.mkdir()
            (config_dir / "config.json").write_text('{"demo_mode": true}')
            wallets_dir = config_dir / "wallets"
            orig_config = utils_mod.CONFIG_DIR
            orig_wallets = utils_mod.WALLETS_DIR
            orig_wallet_file = utils_mod.WALLET_FILE
            orig_legacy = utils_mod.LEGACY_WALLET_FILE
            utils_mod.CONFIG_DIR = config_dir
            utils_mod.WALLETS_DIR = wallets_dir
            utils_mod.WALLET_FILE = config_dir / "wallet.json"
            utils_mod.LEGACY_WALLET_FILE = config_dir / "wallet.json"
            try:
                monkeypatch.setattr(system_mod, "get_config", lambda key, default=None: key == "demo_mode")
                monkeypatch.setattr(system_mod, "load_config", lambda: {"demo_mode": True})
                monkeypatch.setattr(system_mod, "get_demo_private_key", lambda idx: DUMMY_KEY_0)
                ctx = make_ctx()
                system_mod.register_wallet(
                    ctx=ctx, privatekey=None, key_file=None,
                    account=0, keystore=None, name="default",
                )
                saved = wallets_dir / "wallet_default.json"
                assert saved.exists()
            finally:
                utils_mod.CONFIG_DIR = orig_config
                utils_mod.WALLETS_DIR = orig_wallets
                utils_mod.WALLET_FILE = orig_wallet_file
                utils_mod.LEGACY_WALLET_FILE = orig_legacy
        finally:
            import shutil
            shutil.rmtree(bare, ignore_errors=True)


class TestFixBRegression:
    def test_wallet_path_for_name_rejects_escape(self):
        with pytest.raises(ValueError):
            utils_mod.wallet_path_for_name("../evil")

    def test_load_account_rejects_escape(self, temp_config, monkeypatch):
        monkeypatch.setattr(utils_mod, "get_env_key", lambda key, verbose=None: None)
        with pytest.raises((ValueError, FileNotFoundError)):
            utils_mod.load_account(name="../evil")

    def test_cli_wallet_flag_invalid_name_exits(self):
        result = CliRunner().invoke(main_app, ["--wallet", "../evil", "system", "list-accounts"])
        assert result.exit_code == 1

    def test_cli_set_wallet_rejects_invalid_name(self, monkeypatch, temp_config):
        monkeypatch.setattr(system_mod, "resolve_ipfs_config", lambda: SimpleNamespace(provider="env", api_url_add=None, api_url_retrieve=None, api_key=None, api_secret=None, service_path=None))
        result = CliRunner().invoke(main_app, ["system", "set-wallet", "../evil"])
        assert result.exit_code == 1


class TestFixCRegression:
    def test_import_single_level_keystore(self, temp_config, monkeypatch):
        acct = Account.create()
        ks = Account.encrypt(acct.key.hex(), "import-pw")
        ks_path = temp_config["config_dir"] / "test.json"
        ks_path.write_text(json.dumps(ks))

        monkeypatch.setattr(system_mod, "get_config", lambda key, default=None: False)
        monkeypatch.setattr(system_mod, "load_config", lambda: {})
        monkeypatch.setattr(system_mod, "getpass", lambda prompt: "import-pw")

        ctx = make_ctx()
        connect_kwargs = {
            "ctx": ctx, "privatekey": None, "key_file": None,
            "account": None, "keystore": ks_path, "name": "single",
        }
        system_mod.register_wallet(**connect_kwargs)

        saved = temp_config["wallets_dir"] / "wallet_single.json"
        data = json.loads(saved.read_text())
        assert "keystore" in data
        assert "crypto" in data["keystore"]
        assert "keystore" not in data["keystore"]

    def test_reimport_wrapped_keystore_not_double_wrapped(self, temp_config, monkeypatch):
        monkeypatch.setattr(utils_mod, "get_env_key", lambda key, verbose=None: None)
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: DUMMY_PW)
        monkeypatch.setattr(utils_mod, "_cleanup_stale_session", lambda: None)

        ks = Account.encrypt(DUMMY_KEY_0, DUMMY_PW)
        acct = Account.from_key(DUMMY_KEY_0)
        wrapper = {"version": 1, "address": acct.address, "keystore": ks, "source": "imported", "name": "wrapped"}
        wrapped_path = temp_config["wallets_dir"] / "wallet_wrapped.json"
        temp_config["wallets_dir"].mkdir(parents=True, exist_ok=True)
        wrapped_path.write_text(json.dumps(wrapper))

        monkeypatch.setattr(system_mod, "get_config", lambda key, default=None: False)
        monkeypatch.setattr(system_mod, "load_config", lambda: {})
        monkeypatch.setattr(system_mod, "getpass", lambda prompt: DUMMY_PW)

        ctx = make_ctx()
        connect_kwargs = {
            "ctx": ctx, "privatekey": None, "key_file": None,
            "account": None, "keystore": wrapped_path, "name": "reimport",
        }
        system_mod.register_wallet(**connect_kwargs)

        saved = temp_config["wallets_dir"] / "wallet_reimport.json"
        data = json.loads(saved.read_text())
        assert "keystore" in data
        assert "crypto" in data["keystore"]
        assert data["source"] == "imported"
        loaded = utils_mod.load_account(name="reimport")
        assert loaded.address == acct.address


class TestFixERegression:
    def test_set_wallet_persists_config(self, monkeypatch, temp_config):
        config_file = temp_config["config_dir"] / "config.json"
        config_file.write_text("{}")
        orig_config_file = utils_mod.CONFIG_FILE
        utils_mod.CONFIG_FILE = config_file
        monkeypatch.setattr(system_mod, "resolve_ipfs_config", lambda: SimpleNamespace(provider="env", api_url_add=None, api_url_retrieve=None, api_key=None, api_secret=None, service_path=None))
        try:
            (temp_config["wallets_dir"] / "wallet_validator.json").write_text('{"version": 1, "address": "0xTest"}')
            result = CliRunner().invoke(main_app, ["system", "set-wallet", "validator"])
            assert result.exit_code == 0
            plain = _plain(result.output)
            assert "deprecated" in plain
            assert "Active wallet set to 'validator'" in plain
            config = utils_mod.load_config()
            assert config.get("wallet_name") == "validator"
        finally:
            utils_mod.CONFIG_FILE = orig_config_file

    def test_connect_wallet_persists_config(self, monkeypatch, temp_config):
        config_file = temp_config["config_dir"] / "config.json"
        config_file.write_text("{}")
        orig_config_file = utils_mod.CONFIG_FILE
        utils_mod.CONFIG_FILE = config_file
        monkeypatch.setattr(system_mod, "resolve_ipfs_config", lambda: SimpleNamespace(provider="env", api_url_add=None, api_url_retrieve=None, api_key=None, api_secret=None, service_path=None))
        try:
            (temp_config["wallets_dir"] / "wallet_validator.json").write_text('{"version": 1, "address": "0xTest"}')
            result = CliRunner().invoke(main_app, ["system", "connect-wallet", "validator"])
            assert result.exit_code == 0
            plain = _plain(result.output)
            assert "Active wallet set to 'validator'" in plain
            assert "0xTest" in plain
            config = utils_mod.load_config()
            assert config.get("wallet_name") == "validator"
        finally:
            utils_mod.CONFIG_FILE = orig_config_file

    def test_connect_wallet_unregistered_name_exits(self, monkeypatch, temp_config):
        monkeypatch.setattr(system_mod, "resolve_ipfs_config", lambda: SimpleNamespace(provider="env", api_url_add=None, api_url_retrieve=None, api_key=None, api_secret=None, service_path=None))
        result = CliRunner().invoke(main_app, ["system", "connect-wallet", "ghost"])
        assert result.exit_code == 1
        assert "register-wallet" in _plain(result.output)

    def test_connect_wallet_rejects_wallet_flag_trap(self, monkeypatch, temp_config):
        # `--wallet X` is the per-invocation override (hoisted by GlobalOptionsGroup),
        # not the wallet to connect — the guard must point at the positional form.
        monkeypatch.setattr(system_mod, "resolve_ipfs_config", lambda: SimpleNamespace(provider="env", api_url_add=None, api_url_retrieve=None, api_key=None, api_secret=None, service_path=None))
        (temp_config["wallets_dir"] / "wallet_validator.json").write_text('{"version": 1, "address": "0xTest"}')
        result = CliRunner().invoke(main_app, ["system", "connect-wallet", "--wallet", "validator"])
        assert result.exit_code == 1
        assert "Did you mean" in _plain(result.output)


class TestSkipListRouting:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, temp_config):
        monkeypatch.setattr(system_mod, "resolve_ipfs_config",
                            lambda: SimpleNamespace(provider="env", api_url_add=None, api_url_retrieve=None, api_key=None, api_secret=None, service_path=None))
        config_file = temp_config["config_dir"] / "config.json"
        config_file.write_text("{}")

    def test_read_wallet_no_wallet_reaches_command_body(self):
        result = CliRunner().invoke(main_app, ["system", "read-wallet"])
        assert "No wallet found" in result.output

    def test_show_index_no_wallet_reaches_command_body(self):
        result = CliRunner().invoke(main_app, ["system", "show-index", "--address", "0x0000000000000000000000000000000000000000"])
        assert result.exit_code == 1

    def test_set_wallet_no_wallet_reaches_command_body(self):
        result = CliRunner().invoke(main_app, ["system", "set-wallet", "test-name"])
        # Command body is reached (not blocked by the system callback);
        # exits 1 because wallet "test-name" does not exist on disk.
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


def _write_encrypted_wallet(wallets_dir, name, key, pw):
    """Write a wrapper-schema encrypted keystore to wallet_<name>.json; return the address."""
    ks = Account.encrypt(key, pw)
    acct = Account.from_key(key)
    wrapper = {"version": 1, "address": acct.address, "keystore": ks,
               "source": "created", "name": name}
    (wallets_dir / f"wallet_{name}.json").write_text(json.dumps(wrapper))
    return acct.address


class TestRegisterWalletOverwriteGuard:
    """Review fix #2: confirm before overwriting an existing named keystore."""

    def _base_monkeypatch(self, monkeypatch):
        monkeypatch.setattr(system_mod, "get_config", lambda key, default=None: False)
        monkeypatch.setattr(system_mod, "load_config", lambda: {})
        monkeypatch.setattr(system_mod, "getpass", lambda prompt: DUMMY_PW)
        # Deterministic: no DIN_WALLET_PASSWORD from the ambient .env.
        monkeypatch.setattr(utils_mod, "get_env_key", lambda *a, **k: None)

    def test_omitted_yes_prompts_and_aborts(self, temp_config, monkeypatch):
        # `yes` omitted entirely -> Typer passes a truthy OptionInfo; the guard must
        # still fire (normalization). Declining leaves the existing wallet untouched.
        _write_encrypted_wallet(temp_config["wallets_dir"], "prod", DUMMY_KEY_0, DUMMY_PW)
        before = (temp_config["wallets_dir"] / "wallet_prod.json").read_text()
        self._base_monkeypatch(monkeypatch)
        monkeypatch.setattr(typer, "confirm", lambda *a, **k: False)

        ctx = make_ctx()
        with pytest.raises(typer.Exit):
            system_mod.register_wallet(
                ctx=ctx, privatekey=DUMMY_KEY_1, key_file=None,
                account=None, keystore=None, name="prod",  # `yes` intentionally omitted
            )

        after = (temp_config["wallets_dir"] / "wallet_prod.json").read_text()
        assert after == before

    def test_explicit_yes_false_confirm_declined_aborts(self, temp_config, monkeypatch):
        _write_encrypted_wallet(temp_config["wallets_dir"], "prod", DUMMY_KEY_0, DUMMY_PW)
        before = (temp_config["wallets_dir"] / "wallet_prod.json").read_text()
        self._base_monkeypatch(monkeypatch)
        monkeypatch.setattr(typer, "confirm", lambda *a, **k: False)

        ctx = make_ctx()
        with pytest.raises(typer.Exit):
            system_mod.register_wallet(
                ctx=ctx, privatekey=DUMMY_KEY_1, key_file=None,
                account=None, keystore=None, name="prod", yes=False,
            )
        after = (temp_config["wallets_dir"] / "wallet_prod.json").read_text()
        assert after == before

    def test_confirm_accepted_replaces(self, temp_config, monkeypatch):
        old_addr = _write_encrypted_wallet(temp_config["wallets_dir"], "prod", DUMMY_KEY_0, DUMMY_PW)
        self._base_monkeypatch(monkeypatch)
        monkeypatch.setattr(typer, "confirm", lambda *a, **k: True)

        ctx = make_ctx()
        system_mod.register_wallet(
            ctx=ctx, privatekey=DUMMY_KEY_1, key_file=None,
            account=None, keystore=None, name="prod", yes=False,
        )
        data = json.loads((temp_config["wallets_dir"] / "wallet_prod.json").read_text())
        assert data["address"] == Account.from_key(DUMMY_KEY_1).address
        assert data["address"] != old_addr

    def test_yes_true_skips_confirm(self, temp_config, monkeypatch):
        _write_encrypted_wallet(temp_config["wallets_dir"], "prod", DUMMY_KEY_0, DUMMY_PW)
        self._base_monkeypatch(monkeypatch)
        called = []
        monkeypatch.setattr(typer, "confirm", lambda *a, **k: called.append(True) or True)

        ctx = make_ctx()
        system_mod.register_wallet(
            ctx=ctx, privatekey=DUMMY_KEY_1, key_file=None,
            account=None, keystore=None, name="prod", yes=True,
        )
        assert called == []  # confirm never invoked
        data = json.loads((temp_config["wallets_dir"] / "wallet_prod.json").read_text())
        assert data["address"] == Account.from_key(DUMMY_KEY_1).address

    def test_doomed_keystore_input_no_prompt(self, temp_config, monkeypatch):
        # A missing keystore must fail fast BEFORE the overwrite prompt (validation
        # precedes the guard), so `typer.confirm` is never reached.
        _write_encrypted_wallet(temp_config["wallets_dir"], "prod", DUMMY_KEY_0, DUMMY_PW)
        self._base_monkeypatch(monkeypatch)
        called = []
        monkeypatch.setattr(typer, "confirm", lambda *a, **k: called.append(True) or True)

        ctx = make_ctx()
        with pytest.raises(typer.Exit):
            system_mod.register_wallet(
                ctx=ctx, privatekey=None, key_file=None, account=None,
                keystore=Path("/nonexistent/ks.json"), name="prod", yes=False,
            )
        assert called == []


class TestNewWalletPasswordNotCached:
    """Review fix #3: creating/overwriting a wallet must not reuse a stale cached password."""

    def test_create_ignores_cached_password(self, temp_config, monkeypatch):
        utils_mod._PASSWORD_CACHE.clear()
        # Seed a stale cached password for the same name, as a prior load_account would.
        utils_mod._PASSWORD_CACHE["prod"] = ("stale-cached-pw", utils_mod.time.time() + 10_000)

        monkeypatch.setattr(system_mod, "get_config", lambda key, default=None: False)
        monkeypatch.setattr(system_mod, "load_config", lambda: {})
        monkeypatch.setattr(utils_mod, "get_env_key", lambda *a, **k: None)
        monkeypatch.setattr(system_mod, "getpass", lambda prompt: "fresh-pw")

        ctx = make_ctx()
        system_mod.register_wallet(
            ctx=ctx, privatekey=DUMMY_KEY_0, key_file=None,
            account=None, keystore=None, name="prod", yes=True,
        )

        wrapper = json.loads((temp_config["wallets_dir"] / "wallet_prod.json").read_text())
        expected = Account.from_key(DUMMY_KEY_0).address
        # Encrypted with the freshly-entered password, NOT the stale cached one.
        assert Account.from_key(Account.decrypt(wrapper["keystore"], "fresh-pw")).address == expected
        with pytest.raises(ValueError):
            Account.decrypt(wrapper["keystore"], "stale-cached-pw")


class TestSingleEnvParseOnUnlock:
    """Review fix #5: one DIN_WALLET_PASSWORD fetch (=> one .env parse) per unlock."""

    def test_load_account_fetches_env_password_once(self, temp_config, monkeypatch):
        utils_mod._PASSWORD_CACHE.clear()
        ks = Account.encrypt(DUMMY_KEY_0, DUMMY_PW)
        acct = Account.from_key(DUMMY_KEY_0)
        wrapper = {"version": 1, "address": acct.address, "keystore": ks,
                   "source": "created", "name": "prod"}
        (temp_config["wallets_dir"] / "wallet_prod.json").write_text(json.dumps(wrapper))

        calls = []

        def counting_get_env_key(key, *args, **kwargs):
            calls.append(key)
            return None

        monkeypatch.setattr(utils_mod, "get_env_key", counting_get_env_key)
        monkeypatch.setattr(utils_mod, "getpass", lambda prompt: DUMMY_PW)
        monkeypatch.setattr(utils_mod, "_cleanup_stale_session", lambda: None)

        loaded = utils_mod.load_account(name="prod")
        assert loaded.address == acct.address
        assert calls.count("DIN_WALLET_PASSWORD") == 1


_PASSWORD_TTL_DEFAULT = 900

