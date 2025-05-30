import asyncio
import logging

import boto3
import click

from plldb.debugger import Debugger
from plldb.rest_client import RestApiClient
from plldb.setup import BootstrapManager
from plldb.simulator import start_simulator
from plldb.stack_discovery import StackDiscovery
from plldb.websocket_client import WebSocketClient


@click.group()
@click.version_option(prog_name="plldb")
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging")
@click.pass_context
def cli(ctx, debug: bool):
    """PLLDB - AWS Command Line Tool"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if debug:
        logging.getLogger("plldb").setLevel(logging.DEBUG)
        logger = logging.getLogger(__name__)
        logger.debug("Debug mode enabled")

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
@click.option("--debugpy", is_flag=True, default=False, help="Enable debugpy server")
@click.option("--debugpy-port", default=5678, type=int, help="Port for the debugpy server (default: 5678)")
@click.option("--debugpy-host", default="127.0.0.1", help="Host for the debugpy server (default: 127.0.0.1)")
@click.pass_context
def attach(ctx, stack_name: str, debugpy: bool, debugpy_port: int, debugpy_host: str):
    """Attach debugger to a CloudFormation stack"""
    session = ctx.obj["session"]

    try:
        # Start debugpy server if enabled
        if debugpy:
            import debugpy as debugpy_module

            debugpy_module.listen((debugpy_host, debugpy_port))
            click.echo(f"Debugpy server is enabled and it runs on {debugpy_host}:{debugpy_port}.")
            click.echo("To attach to the debugpy server from the visual studio code, you can use the following launch configuration:")
            click.echo("")
            click.echo("{")
            click.echo('    "name": "Python Debugger: Remote Attach",')
            click.echo('    "type": "debugpy",')
            click.echo('    "request": "attach",')
            click.echo(f'    "connect": {{ "host": "{debugpy_host}", "port": {debugpy_port} }}')
            click.echo("}")
            click.echo("")
            click.echo("If you don't have your debug configurations yet, create `.vscode/launch.json` file with the following content:")
            click.echo("")
            click.echo("{")
            click.echo('    "configurations": [')
            click.echo('        "name": "Python Debugger: Remote Attach",')
            click.echo('        "type": "debugpy",')
            click.echo('        "request": "attach",')
            click.echo(f'        "connect": {{ "host": "{debugpy_host}", "port": {debugpy_port} }}')
            click.echo("    ]")
            click.echo("}")
            click.echo("")
            click.echo("Waiting for debugger to attach...")
            debugpy_module.wait_for_client()
            click.echo("Debugger attached!")

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
        debugger = Debugger(session=session, stack_name=stack_name)
        asyncio.run(ws_client.run_loop(debugger.handle_message))

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except KeyboardInterrupt:
        click.echo("\nDebugger session terminated")
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        ctx.exit(1)


@cli.group(invoke_without_command=True)
@click.pass_context
def simulator(ctx):
    """Local Lambda function simulator"""
    if ctx.invoked_subcommand is None:
        ctx.invoke(simulator_start)


@simulator.command("start")
@click.option(
    "-t",
    "--template",
    help="Path to CloudFormation template. If relative, resolved from current directory",
)
@click.option(
    "-d",
    "--directory",
    help="Working directory for simulator. Cannot be used with absolute template path",
)
@click.pass_context
def simulator_start(ctx, template: str, directory: str):
    """Start the local Lambda function simulator"""
    try:
        start_simulator(template=template, directory=directory)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except KeyboardInterrupt:
        pass  # Handled in simulator
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        ctx.exit(1)


if __name__ == "__main__":
    cli()
