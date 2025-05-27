import click
import boto3


@click.group()
@click.version_option(prog_name="plldb")
@click.pass_context
def cli(ctx):
    """PLLDB - AWS Command Line Tool"""

    session = boto3.Session()
    boto3.setup_default_session(botocore_session=session._session)
    ctx.ensure_object(dict)
    ctx.obj["session"] = session


if __name__ == "__main__":
    cli()
