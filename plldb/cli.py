import asyncio
import logging

import boto3
import click

from plldb.debugger import Debugger
from plldb.setup import BootstrapManager
from plldb.rest_client import RestApiClient
from plldb.stack_discovery import StackDiscovery
from plldb.websocket_client import WebSocketClient

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


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


@cli.command()
@click.option("--stack-name", required=True, help="Name of the CloudFormation stack to attach to")
@click.pass_context
def attach(ctx, stack_name: str):
    """Attach debugger to a CloudFormation stack"""
    session = ctx.obj["session"]

    try:
        # Discover stack endpoints
        discovery = StackDiscovery(session)
        endpoints = discovery.get_api_endpoints("plldb")

        click.echo(f"Discovered endpoints for stack plldb")

        # Create debug session via REST API
        rest_client = RestApiClient(session)
        session_id = rest_client.create_session(endpoints["rest_api_url"], stack_name)

        click.echo(f"Created debug session: {session_id}")
        click.echo("Connecting to WebSocket API...")

        # Connect to WebSocket and run message loop
        ws_client = WebSocketClient(endpoints["websocket_url"], session_id)

        # Run the async event loop
        debugger = Debugger(stack_name=stack_name)
        asyncio.run(ws_client.run_loop(debugger.handle_message))

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except KeyboardInterrupt:
        click.echo("\nDebugger session terminated")
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        ctx.exit(1)


if __name__ == "__main__":
    cli()
