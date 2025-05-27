import logging

import boto3
import click

from plldb.bootstrap.setup import BootstrapManager

logging.basicConfig(level=logging.INFO, format="%(message)s")


@click.group()
@click.version_option(prog_name="plldb")
@click.pass_context
def cli(ctx):
    """PLLDB - AWS Command Line Tool"""

    session = boto3.Session()
    ctx.ensure_object(dict)
    ctx.obj["session"] = session


@cli.group(invoke_without_command=True)
@click.pass_context
def bootstrap(ctx):
    """Bootstrap the core infrastructure"""
    if ctx.invoked_subcommand is None:
        ctx.invoke(setup)


@bootstrap.command()
@click.pass_context
def setup(ctx):
    """Create the S3 bucket and upload the core infrastructure"""
    session = ctx.obj["session"]
    manager = BootstrapManager(session)
    manager.setup()


@bootstrap.command()
@click.pass_context
def destroy(ctx):
    """Destroy the S3 bucket and remove the core infrastructure"""
    session = ctx.obj["session"]
    manager = BootstrapManager(session)
    manager.destroy()


if __name__ == "__main__":
    cli()
