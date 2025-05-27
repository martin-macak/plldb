import boto3
import pytest
from click.testing import CliRunner

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


def test_bootstrap_command_exists(runner):
    result = runner.invoke(cli, ["bootstrap", "--help"])
    assert result.exit_code == 0
    assert "Bootstrap the core infrastructure" in result.output


def test_bootstrap_setup_command_exists(runner):
    result = runner.invoke(cli, ["bootstrap", "setup", "--help"])
    assert result.exit_code == 0
    assert "Create the S3 bucket and upload the core infrastructure" in result.output


def test_bootstrap_destroy_command_exists(runner):
    result = runner.invoke(cli, ["bootstrap", "destroy", "--help"])
    assert result.exit_code == 0
    assert "Destroy the S3 bucket and remove the core infrastructure" in result.output


def test_bootstrap_without_subcommand_runs_setup(runner, mock_aws_session, monkeypatch):
    # Mock the boto3 Session to return our mocked session
    def mock_session_factory(*args, **kwargs):
        return mock_aws_session

    monkeypatch.setattr(boto3, "Session", mock_session_factory)

    # Mock the BootstrapManager methods that would cause CloudFormation issues
    from plldb.bootstrap.setup import BootstrapManager

    monkeypatch.setattr(BootstrapManager, "_upload_lambda_functions", lambda self, bucket_name: None)
    monkeypatch.setattr(BootstrapManager, "_upload_template", lambda self, bucket_name: "test-key")
    monkeypatch.setattr(BootstrapManager, "_deploy_stack", lambda self, bucket_name, template_key: None)

    result = runner.invoke(cli, ["bootstrap"])

    if result.exit_code != 0:
        print(f"Exit code: {result.exit_code}")
        print(f"Output: {result.output}")
        print(f"Exception: {result.exception}")
    assert result.exit_code == 0
    assert "Setting up core infrastructure bucket" in result.output
    assert "Bootstrap setup completed successfully" in result.output
