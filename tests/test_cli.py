from unittest.mock import Mock, patch

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
    assert "plldb, version" in result.output
    # Version should be in the format: plldb, version X.Y.Z or plldb, version X.Y.Z.postN.devM+hash
    assert result.output.startswith("plldb, version ")


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
    def mock_session_factory():
        return mock_aws_session

    monkeypatch.setattr(boto3, "Session", mock_session_factory)

    # Mock the BootstrapManager methods that would cause CloudFormation issues
    from plldb.setup import BootstrapManager

    monkeypatch.setattr(BootstrapManager, "_upload_lambda_functions", lambda *args: None)
    monkeypatch.setattr(BootstrapManager, "_upload_template", lambda *args: "test-key")
    monkeypatch.setattr(BootstrapManager, "_deploy_stack", lambda *args: None)

    result = runner.invoke(cli, ["bootstrap"])

    if result.exit_code != 0:
        print(f"Exit code: {result.exit_code}")
        print(f"Output: {result.output}")
        print(f"Exception: {result.exception}")
    assert result.exit_code == 0
    assert "Setting up core infrastructure bucket" in result.output
    assert "Bootstrap setup completed successfully" in result.output


def test_attach_command_help(runner):
    result = runner.invoke(cli, ["attach", "--help"])
    assert result.exit_code == 0
    assert "Attach debugger to a CloudFormation stack" in result.output
    assert "--stack-name" in result.output
    assert "--debugpy" in result.output
    assert "--debugpy-port" in result.output
    assert "--debugpy-host" in result.output


def test_attach_command_requires_stack_name(runner):
    result = runner.invoke(cli, ["attach"])
    assert result.exit_code != 0
    assert "Missing option '--stack-name'" in result.output


@patch("plldb.cli.Debugger")
@patch("plldb.cli.StackDiscovery")
@patch("plldb.cli.RestApiClient")
@patch("plldb.cli.WebSocketClient")
@patch("plldb.cli.asyncio.run")
def test_attach_command_success(mock_asyncio_run, mock_ws_client_class, mock_rest_client_class, mock_discovery_class, mock_debugger_class, runner, mock_aws_session, monkeypatch):
    """Test successful attach command execution."""

    # Mock boto3 Session
    def mock_session_factory():
        return mock_aws_session

    monkeypatch.setattr(boto3, "Session", mock_session_factory)

    # Mock stack discovery
    mock_discovery = Mock()
    mock_discovery.get_api_endpoints.return_value = {
        "websocket_url": "wss://test.execute-api.us-east-1.amazonaws.com/prod",
        "rest_api_url": "https://test.execute-api.us-east-1.amazonaws.com/prod",
    }
    mock_discovery_class.return_value = mock_discovery

    # Mock REST client
    mock_rest_client = Mock()
    mock_rest_client.create_session.return_value = "test-session-id"
    mock_rest_client_class.return_value = mock_rest_client

    # Mock WebSocket client
    mock_ws_client = Mock()
    mock_ws_client_class.return_value = mock_ws_client

    # Mock Debugger
    mock_debugger = Mock()
    mock_debugger_class.return_value = mock_debugger

    # Run command without --debugpy flag (debugpy disabled by default)
    result = runner.invoke(cli, ["attach", "--stack-name", "test-stack"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Discovered endpoints for stack plldb" in result.output
    assert "Created debug session: test-session-id" in result.output
    assert "Connecting to WebSocket API..." in result.output
    # Should not have debugpy messages
    assert "Debugpy server is enabled" not in result.output

    # Verify calls
    mock_discovery.get_api_endpoints.assert_called_once_with("plldb")
    mock_rest_client.create_session.assert_called_once_with("https://test.execute-api.us-east-1.amazonaws.com/prod", "test-stack")
    mock_ws_client_class.assert_called_once_with("wss://test.execute-api.us-east-1.amazonaws.com/prod", "test-session-id")
    mock_debugger_class.assert_called_once_with(session=mock_aws_session, stack_name="test-stack")
    mock_asyncio_run.assert_called_once()


@patch("debugpy.listen")
@patch("debugpy.wait_for_client")
@patch("plldb.cli.Debugger")
@patch("plldb.cli.StackDiscovery")
@patch("plldb.cli.RestApiClient")
@patch("plldb.cli.WebSocketClient")
@patch("plldb.cli.asyncio.run")
def test_attach_command_with_debugpy(
    _, mock_ws_client_class, mock_rest_client_class, mock_discovery_class, mock_debugger_class, mock_wait_for_client, mock_listen, runner, mock_aws_session, monkeypatch
):
    """Test attach command with debugpy enabled."""

    # Mock boto3 Session
    def mock_session_factory():
        return mock_aws_session

    monkeypatch.setattr(boto3, "Session", mock_session_factory)

    # Mock stack discovery
    mock_discovery = Mock()
    mock_discovery.get_api_endpoints.return_value = {
        "websocket_url": "wss://test.execute-api.us-east-1.amazonaws.com/prod",
        "rest_api_url": "https://test.execute-api.us-east-1.amazonaws.com/prod",
    }
    mock_discovery_class.return_value = mock_discovery

    # Mock REST client
    mock_rest_client = Mock()
    mock_rest_client.create_session.return_value = "test-session-id"
    mock_rest_client_class.return_value = mock_rest_client

    # Mock WebSocket client
    mock_ws_client = Mock()
    mock_ws_client_class.return_value = mock_ws_client

    # Mock Debugger
    mock_debugger = Mock()
    mock_debugger_class.return_value = mock_debugger

    # Run command with --debugpy flag to enable debugpy
    result = runner.invoke(cli, ["attach", "--stack-name", "test-stack", "--debugpy", "--debugpy-port", "5679", "--debugpy-host", "0.0.0.0"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Debugpy server is enabled and it runs on 0.0.0.0:5679." in result.output
    assert "To attach to the debugpy server from the visual studio code" in result.output
    assert '"name": "Python Debugger: Remote Attach"' in result.output
    assert '"connect": { "host": "0.0.0.0", "port": 5679 }' in result.output
    assert "Waiting for debugger to attach..." in result.output
    assert "Debugger attached!" in result.output

    # Verify debugpy calls
    mock_listen.assert_called_once_with(("0.0.0.0", 5679))
    mock_wait_for_client.assert_called_once()


@patch("plldb.cli.StackDiscovery")
def test_attach_command_stack_not_found(mock_discovery_class, runner, mock_aws_session, monkeypatch):
    """Test attach command when stack is not found."""

    # Mock boto3 Session
    def mock_session_factory():
        return mock_aws_session

    monkeypatch.setattr(boto3, "Session", mock_session_factory)

    # Mock stack discovery to raise error
    mock_discovery = Mock()
    mock_discovery.get_api_endpoints.side_effect = ValueError("Stack 'plldb' not found")
    mock_discovery_class.return_value = mock_discovery

    # Run command without --debugpy (debugpy disabled by default)
    result = runner.invoke(cli, ["attach", "--stack-name", "test-stack"])

    assert result.exit_code == 1
    assert "Error: Stack 'plldb' not found" in result.output
