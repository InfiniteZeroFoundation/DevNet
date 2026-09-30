"""Demo-key selection must survive the root callback's network selection."""
from eth_account import Account
from dincli.cli.context import DinContext
from dincli.sdk import config
from dincli.cli import context, utils


def test_demo_signer_survives_network_selection(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'CONFIG_FILE', tmp_path / 'config.json')
    monkeypatch.setattr(context, 'get_config', lambda key, default=None: True if key == 'demo_mode' else default)
    private_key = '0x' + '32' * 32
    monkeypatch.setattr(utils, 'get_demo_private_key', lambda index: private_key)
    ctx = DinContext()
    ctx.select_demo_account(0)
    signer = ctx.session.signer
    ctx.select_network('local')
    assert ctx.session.signer is signer
    assert ctx.session.network == 'local'
    assert ctx.session.address == ctx.account.address == Account.from_key(private_key).address
    assert ctx.resolved_wallet_name == 'demo-0'
