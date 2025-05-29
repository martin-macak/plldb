import json
import pytest
from unittest.mock import MagicMock, patch
from plldb.cloudformation.lambda_functions.debugger_instrumentation import (
    lambda_handler,
    instrument_lambda_functions,
    uninstrument_lambda_functions,
    get_latest_layer_version,
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
        mock_lambda_client.get_function_configuration.side_effect = [
            {"Environment": {"Variables": {}}, "Layers": [], "Role": "arn:aws:iam::123456789012:role/test-function-1-role"},
            {"Environment": {"Variables": {}}, "Layers": [], "Role": "arn:aws:iam::123456789012:role/test-function-2-role"},
        ]
        # Mock list_layer_versions for get_latest_layer_version
        mock_lambda_client.list_layer_versions.return_value = {
            "LayerVersions": [
                {"LayerVersionArn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:3", "Version": 3},
                {"LayerVersionArn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:2", "Version": 2},
                {"LayerVersionArn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1", "Version": 1},
            ]
        }

        # Mock IAM client
        mock_iam_client = MagicMock()
        mock_iam_client.exceptions.NoSuchEntityException = Exception

        # Mock STS client
        mock_sts_client = MagicMock()
        mock_sts_client.get_caller_identity.return_value = {"Account": "123456789012"}

        # Configure boto3.client to return appropriate mocks
        def get_client(service):
            if service == "cloudformation":
                return mock_cf_client
            elif service == "lambda":
                return mock_lambda_client
            elif service == "iam":
                return mock_iam_client
            elif service == "sts":
                return mock_sts_client
            else:
                raise ValueError(f"Unexpected service: {service}")

        mock_boto3.client.side_effect = get_client

        yield {"boto3": mock_boto3, "cf_client": mock_cf_client, "lambda_client": mock_lambda_client, "iam_client": mock_iam_client, "sts_client": mock_sts_client}


class TestGetLatestLayerVersion:
    """Test get_latest_layer_version function."""

    def test_get_latest_layer_version_success(self, mock_aws_services):
        """Test successful retrieval of latest layer version."""
        result = get_latest_layer_version(mock_aws_services["lambda_client"])

        assert result == "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:3"
        mock_aws_services["lambda_client"].list_layer_versions.assert_called_once_with(LayerName="PLLDBDebuggerRuntime")

    def test_get_latest_layer_version_no_versions(self, mock_aws_services):
        """Test when no layer versions are found."""
        mock_aws_services["lambda_client"].list_layer_versions.return_value = {"LayerVersions": []}

        result = get_latest_layer_version(mock_aws_services["lambda_client"])

        assert result is None

    def test_get_latest_layer_version_layer_not_found(self, mock_aws_services):
        """Test when layer does not exist."""
        mock_aws_services["lambda_client"].exceptions.ResourceNotFoundException = Exception
        mock_aws_services["lambda_client"].list_layer_versions.side_effect = Exception("Layer not found")

        result = get_latest_layer_version(mock_aws_services["lambda_client"])

        assert result is None

    def test_get_latest_layer_version_general_error(self, mock_aws_services):
        """Test when a general error occurs."""
        mock_aws_services["lambda_client"].list_layer_versions.side_effect = Exception("General error")

        result = get_latest_layer_version(mock_aws_services["lambda_client"])

        assert result is None


class TestInstrumentLambdaFunctions:
    """Test instrument_lambda_functions function."""

    def test_instrument_lambda_functions_success(self, mock_aws_services, monkeypatch):
        """Test successful instrumentation of lambda functions."""
        # Mock the WEBSOCKET_ENDPOINT environment variable
        monkeypatch.setenv("WEBSOCKET_ENDPOINT", "https://test.execute-api.us-east-1.amazonaws.com/prod")

        instrument_lambda_functions("test-stack", "session-123", "connection-456")

        # Verify layer lookup
        mock_aws_services["lambda_client"].list_layer_versions.assert_called_once_with(LayerName="PLLDBDebuggerRuntime")

        # Verify CloudFormation calls
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
            assert kwargs["Environment"]["Variables"]["DEBUGGER_WEBSOCKET_API_ENDPOINT"] == "https://test.execute-api.us-east-1.amazonaws.com/prod"
            assert "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:3" in kwargs["Layers"]

        # Verify IAM policy was added - should be called twice (for two functions)
        assert mock_aws_services["iam_client"].put_role_policy.call_count == 2

        # Check the IAM policy calls
        iam_calls = mock_aws_services["iam_client"].put_role_policy.call_args_list
        for i, call in enumerate(iam_calls):
            args, kwargs = call
            expected_role = f"test-function-{i + 1}-role"
            assert kwargs["RoleName"] == expected_role
            assert kwargs["PolicyName"] == "PLLDBAssumeRolePolicy"
            policy_doc = json.loads(kwargs["PolicyDocument"])
            assert policy_doc["Version"] == "2012-10-17"
            assert len(policy_doc["Statement"]) == 1
            assert policy_doc["Statement"][0]["Effect"] == "Allow"
            assert policy_doc["Statement"][0]["Action"] == "sts:AssumeRole"
            assert policy_doc["Statement"][0]["Resource"] == "arn:aws:iam::123456789012:role/PLLDBDebuggerRole"

    def test_instrument_lambda_functions_idempotent(self, mock_aws_services, monkeypatch):
        """Test that instrumentation is idempotent."""
        # Mock the WEBSOCKET_ENDPOINT environment variable
        monkeypatch.setenv("WEBSOCKET_ENDPOINT", "https://test.execute-api.us-east-1.amazonaws.com/prod")
        # Set up already instrumented function
        mock_aws_services["lambda_client"].get_function_configuration.side_effect = [
            {
                "Environment": {"Variables": {"DEBUGGER_SESSION_ID": "session-123", "DEBUGGER_CONNECTION_ID": "connection-456", "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bin/bootstrap"}},
                "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:3"}],
            },
            {
                "Environment": {"Variables": {"DEBUGGER_SESSION_ID": "session-123", "DEBUGGER_CONNECTION_ID": "connection-456", "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bin/bootstrap"}},
                "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:3"}],
            },
        ]

        instrument_lambda_functions("test-stack", "session-123", "connection-456")

        # Should not update already instrumented functions
        mock_aws_services["lambda_client"].update_function_configuration.assert_not_called()

    def test_instrument_lambda_functions_layer_not_found(self, mock_aws_services):
        """Test instrumentation when layer is not found."""
        # Mock layer not found
        mock_aws_services["lambda_client"].list_layer_versions.return_value = {"LayerVersions": []}

        instrument_lambda_functions("test-stack", "session-123", "connection-456")

        # Should not attempt to update any functions
        mock_aws_services["lambda_client"].update_function_configuration.assert_not_called()
        # Should not even list stack resources since we bail out early
        mock_aws_services["cf_client"].list_stack_resources.assert_not_called()


class TestUninstrumentLambdaFunctions:
    """Test uninstrument_lambda_functions function."""

    def test_uninstrument_lambda_functions_success(self, mock_aws_services):
        """Test successful uninstrumentation of lambda functions."""
        # Set up instrumented function
        mock_aws_services["lambda_client"].get_function_configuration.side_effect = [
            {
                "Environment": {
                    "Variables": {
                        "DEBUGGER_SESSION_ID": "session-123",
                        "DEBUGGER_CONNECTION_ID": "connection-456",
                        "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bin/bootstrap",
                        "DEBUGGER_WEBSOCKET_API_ENDPOINT": "https://test.execute-api.us-east-1.amazonaws.com/prod",
                        "OTHER_VAR": "value",
                    }
                },
                "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:2"}, {"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:OtherLayer:1"}],
                "Role": "arn:aws:iam::123456789012:role/test-function-1-role",
            },
            {
                "Environment": {
                    "Variables": {
                        "DEBUGGER_SESSION_ID": "session-123",
                        "DEBUGGER_CONNECTION_ID": "connection-456",
                        "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bin/bootstrap",
                        "DEBUGGER_WEBSOCKET_API_ENDPOINT": "https://test.execute-api.us-east-1.amazonaws.com/prod",
                        "OTHER_VAR": "value",
                    }
                },
                "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:2"}, {"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:OtherLayer:1"}],
                "Role": "arn:aws:iam::123456789012:role/test-function-2-role",
            },
        ]

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
            assert "DEBUGGER_WEBSOCKET_API_ENDPOINT" not in kwargs["Environment"]["Variables"]
            assert kwargs["Environment"]["Variables"].get("OTHER_VAR") == "value"
            # Should remove only the debug layer
            assert len(kwargs["Layers"]) == 1
            assert kwargs["Layers"][0] == "arn:aws:lambda:us-east-1:123456789012:layer:OtherLayer:1"

        # Verify IAM policy was removed - should be called twice (for two functions)
        assert mock_aws_services["iam_client"].delete_role_policy.call_count == 2

        # Check the IAM policy deletion calls
        iam_calls = mock_aws_services["iam_client"].delete_role_policy.call_args_list
        for i, call in enumerate(iam_calls):
            args, kwargs = call
            expected_role = f"test-function-{i + 1}-role"
            assert kwargs["RoleName"] == expected_role
            assert kwargs["PolicyName"] == "PLLDBAssumeRolePolicy"

    def test_uninstrument_lambda_functions_idempotent(self, mock_aws_services):
        """Test that uninstrumentation is idempotent."""
        # Set up already uninstrumented function
        mock_aws_services["lambda_client"].get_function_configuration.return_value = {"Environment": {"Variables": {"OTHER_VAR": "value"}}, "Layers": []}

        uninstrument_lambda_functions("test-stack")

        # Should not update already uninstrumented functions
        mock_aws_services["lambda_client"].update_function_configuration.assert_not_called()


class TestLambdaHandler:
    """Test lambda_handler function."""

    def test_lambda_handler_instrument_success(self, mock_aws_services, monkeypatch):
        """Test successful instrument command."""
        # Mock the WEBSOCKET_ENDPOINT environment variable
        monkeypatch.setenv("WEBSOCKET_ENDPOINT", "https://test.execute-api.us-east-1.amazonaws.com/prod")

        event = {"command": "instrument", "stackName": "test-stack", "sessionId": "session-123", "connectionId": "connection-456"}

        result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "instrumented successfully" in json.loads(result["body"])["message"]

    def test_lambda_handler_uninstrument_success(self, mock_aws_services):
        """Test successful uninstrument command."""
        event = {"command": "uninstrument", "stackName": "test-stack"}

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

        # Make Lambda layer lookup throw an exception
        mock_aws_services["lambda_client"].list_layer_versions.side_effect = Exception("Test error")

        result = lambda_handler(event, None)

        assert result["statusCode"] == 200  # The handler returns 200 even when instrumentation fails
        assert "instrumented successfully" in json.loads(result["body"])["message"]
