import typer

from dincli.cli.modelownerd.aggregation import aggregation_app
from dincli.cli.modelownerd.auditor_batches import auditor_batches_app
from dincli.cli.modelownerd.deploy import deploy_app
from dincli.cli.modelownerd.gi import gi_app
from dincli.cli.modelownerd.lms import lms_app
from dincli.cli.modelownerd.lms_evaluation import lms_evaluation_app
from dincli.cli.modelownerd.model import model_app
from dincli.cli.modelownerd.setup import (add_slasher)
from dincli.cli.modelownerd.slash import slash_app

app = typer.Typer(help="Commands for Model Owners in DIN.")

app.add_typer(deploy_app, name="deploy")
app.add_typer(model_app, name="model")
app.add_typer(gi_app, name="gi")
app.add_typer(lms_app, name="lms")
app.add_typer(auditor_batches_app, name="auditor-batches")
app.add_typer(lms_evaluation_app, name="lms-evaluation")
app.add_typer(aggregation_app, name="aggregation")
app.add_typer(slash_app, name="slash")
app.command("add-slasher")(add_slasher)

if __name__ == "__main__":
    app()