import pytest
from click.testing import CliRunner
import boto3

from plldb.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


def test_cli_version(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "plldb, version 0.1.0" in result.output


def test_cli_help(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "PLLDB - AWS Command Line Tool" in result.output
