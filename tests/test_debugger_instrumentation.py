import json
import pytest
from unittest.mock import MagicMock, patch
from plldb.cloudformation.lambda_functions.debugger_instrumentation import (
    lambda_handler,
    instrument_lambda_functions,
    uninstrument_lambda_functions,
)


@pytest.fixture
def mock_aws_services():
    """Mock AWS services for testing."""
    with patch("plldb.cloudformation.lambda_functions.debugger_instrumentation.boto3") as mock_boto3:
        # Mock CloudFormation client
        mock_cf_client = MagicMock()
        mock_cf_client.describe_stacks.return_value = {
            "Stacks": [{"Outputs": [{"OutputKey": "DebuggerLayerArn", "OutputValue": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"}]}]
        }
        mock_cf_client.list_stack_resources.return_value = {
            "StackResourceSummaries": [
                {"ResourceType": "AWS::Lambda::Function", "PhysicalResourceId": "test-function-1", "LogicalResourceId": "TestFunction1"},
                {"ResourceType": "AWS::Lambda::Function", "PhysicalResourceId": "test-function-2", "LogicalResourceId": "TestFunction2"},
                {"ResourceType": "AWS::S3::Bucket", "PhysicalResourceId": "test-bucket", "LogicalResourceId": "TestBucket"},
            ]
        }

        # Mock Lambda client
        mock_lambda_client = MagicMock()
        # Return different configs for each function
        mock_lambda_client.get_function_configuration.side_effect = [{"Environment": {"Variables": {}}, "Layers": []}, {"Environment": {"Variables": {}}, "Layers": []}]

        # Configure boto3.client to return appropriate mocks
        def get_client(service):
            if service == "cloudformation":
                return mock_cf_client
            elif service == "lambda":
                return mock_lambda_client
            else:
                raise ValueError(f"Unexpected service: {service}")

        mock_boto3.client.side_effect = get_client

        yield {"boto3": mock_boto3, "cf_client": mock_cf_client, "lambda_client": mock_lambda_client}


class TestInstrumentLambdaFunctions:
    """Test instrument_lambda_functions function."""

    def test_instrument_lambda_functions_success(self, mock_aws_services):
        """Test successful instrumentation of lambda functions."""
        with patch.dict("os.environ", {"AWS_CLOUDFORMATION_STACK_NAME": "plldb-infrastructure"}):
            instrument_lambda_functions("test-stack", "session-123", "connection-456")

        # Verify CloudFormation calls
        mock_aws_services["cf_client"].describe_stacks.assert_called_once()
        mock_aws_services["cf_client"].list_stack_resources.assert_called_once_with(StackName="test-stack")

        # Verify Lambda calls - should be called twice (for two functions)
        assert mock_aws_services["lambda_client"].get_function_configuration.call_count == 2
        assert mock_aws_services["lambda_client"].update_function_configuration.call_count == 2

        # Check the update calls
        calls = mock_aws_services["lambda_client"].update_function_configuration.call_args_list
        for call in calls:
            args, kwargs = call
            assert "Environment" in kwargs
            assert kwargs["Environment"]["Variables"]["DEBUGGER_SESSION_ID"] == "session-123"
            assert kwargs["Environment"]["Variables"]["DEBUGGER_CONNECTION_ID"] == "connection-456"
            assert kwargs["Environment"]["Variables"]["AWS_LAMBDA_EXEC_WRAPPER"] == "/opt/bin/bootstrap"
            assert "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1" in kwargs["Layers"]

    def test_instrument_lambda_functions_idempotent(self, mock_aws_services):
        """Test that instrumentation is idempotent."""
        # Set up already instrumented function
        mock_aws_services["lambda_client"].get_function_configuration.side_effect = [
            {
                "Environment": {"Variables": {"DEBUGGER_SESSION_ID": "session-123", "DEBUGGER_CONNECTION_ID": "connection-456", "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bin/bootstrap"}},
                "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"}],
            },
            {
                "Environment": {"Variables": {"DEBUGGER_SESSION_ID": "session-123", "DEBUGGER_CONNECTION_ID": "connection-456", "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bin/bootstrap"}},
                "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"}],
            },
        ]

        with patch.dict("os.environ", {"AWS_CLOUDFORMATION_STACK_NAME": "plldb-infrastructure"}):
            instrument_lambda_functions("test-stack", "session-123", "connection-456")

        # Should not update already instrumented functions
        mock_aws_services["lambda_client"].update_function_configuration.assert_not_called()


class TestUninstrumentLambdaFunctions:
    """Test uninstrument_lambda_functions function."""

    def test_uninstrument_lambda_functions_success(self, mock_aws_services):
        """Test successful uninstrumentation of lambda functions."""
        # Set up instrumented function
        mock_aws_services["lambda_client"].get_function_configuration.side_effect = [
            {
                "Environment": {"Variables": {"DEBUGGER_SESSION_ID": "session-123", "DEBUGGER_CONNECTION_ID": "connection-456", "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bin/bootstrap", "OTHER_VAR": "value"}},
                "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"}, {"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:OtherLayer:1"}],
            },
            {
                "Environment": {"Variables": {"DEBUGGER_SESSION_ID": "session-123", "DEBUGGER_CONNECTION_ID": "connection-456", "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bin/bootstrap", "OTHER_VAR": "value"}},
                "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"}, {"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:OtherLayer:1"}],
            },
        ]

        with patch.dict("os.environ", {"AWS_CLOUDFORMATION_STACK_NAME": "plldb-infrastructure"}):
            uninstrument_lambda_functions("test-stack")

        # Verify Lambda calls
        assert mock_aws_services["lambda_client"].update_function_configuration.call_count == 2

        # Check the update calls
        calls = mock_aws_services["lambda_client"].update_function_configuration.call_args_list
        for call in calls:
            args, kwargs = call
            assert "Environment" in kwargs
            # Should keep OTHER_VAR but remove debug vars
            assert "DEBUGGER_SESSION_ID" not in kwargs["Environment"]["Variables"]
            assert "DEBUGGER_CONNECTION_ID" not in kwargs["Environment"]["Variables"]
            assert "AWS_LAMBDA_EXEC_WRAPPER" not in kwargs["Environment"]["Variables"]
            assert kwargs["Environment"]["Variables"].get("OTHER_VAR") == "value"
            # Should remove only the debug layer
            assert len(kwargs["Layers"]) == 1
            assert kwargs["Layers"][0] == "arn:aws:lambda:us-east-1:123456789012:layer:OtherLayer:1"

    def test_uninstrument_lambda_functions_idempotent(self, mock_aws_services):
        """Test that uninstrumentation is idempotent."""
        # Set up already uninstrumented function
        mock_aws_services["lambda_client"].get_function_configuration.return_value = {"Environment": {"Variables": {"OTHER_VAR": "value"}}, "Layers": []}

        with patch.dict("os.environ", {"AWS_CLOUDFORMATION_STACK_NAME": "plldb-infrastructure"}):
            uninstrument_lambda_functions("test-stack")

        # Should not update already uninstrumented functions
        mock_aws_services["lambda_client"].update_function_configuration.assert_not_called()


class TestLambdaHandler:
    """Test lambda_handler function."""

    def test_lambda_handler_instrument_success(self, mock_aws_services):
        """Test successful instrument command."""
        event = {"command": "instrument", "stackName": "test-stack", "sessionId": "session-123", "connectionId": "connection-456"}

        with patch.dict("os.environ", {"AWS_CLOUDFORMATION_STACK_NAME": "plldb-infrastructure"}):
            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "instrumented successfully" in json.loads(result["body"])["message"]

    def test_lambda_handler_uninstrument_success(self, mock_aws_services):
        """Test successful uninstrument command."""
        event = {"command": "uninstrument", "stackName": "test-stack"}

        with patch.dict("os.environ", {"AWS_CLOUDFORMATION_STACK_NAME": "plldb-infrastructure"}):
            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "uninstrumented successfully" in json.loads(result["body"])["message"]

    def test_lambda_handler_missing_required_params(self):
        """Test lambda handler with missing required parameters."""
        event = {"command": "instrument"}  # Missing stackName

        result = lambda_handler(event, None)

        assert result["statusCode"] == 400
        assert "Missing required parameters" in json.loads(result["body"])["error"]

    def test_lambda_handler_instrument_missing_session_params(self):
        """Test instrument command with missing session parameters."""
        event = {
            "command": "instrument",
            "stackName": "test-stack",
            # Missing sessionId and connectionId
        }

        result = lambda_handler(event, None)

        assert result["statusCode"] == 400
        assert "sessionId and connectionId" in json.loads(result["body"])["error"]

    def test_lambda_handler_unknown_command(self):
        """Test lambda handler with unknown command."""
        event = {"command": "unknown", "stackName": "test-stack"}

        result = lambda_handler(event, None)

        assert result["statusCode"] == 400
        assert "Unknown command" in json.loads(result["body"])["error"]

    def test_lambda_handler_exception(self, mock_aws_services):
        """Test lambda handler exception handling."""
        event = {"command": "instrument", "stackName": "test-stack", "sessionId": "session-123", "connectionId": "connection-456"}

        # Make CloudFormation throw an exception
        mock_aws_services["cf_client"].describe_stacks.side_effect = Exception("Test error")

        with patch.dict("os.environ", {"AWS_CLOUDFORMATION_STACK_NAME": "plldb-infrastructure"}):
            result = lambda_handler(event, None)

        assert result["statusCode"] == 500
        assert "Test error" in json.loads(result["body"])["error"]
