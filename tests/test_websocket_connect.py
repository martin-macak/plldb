"""Tests for WebSocket connect Lambda function."""

import json
from unittest.mock import Mock, patch
from plldb.cloudformation.lambda_functions.websocket_connect import lambda_handler, instrument_lambda_functions


class TestWebSocketConnect:
    """Test WebSocket connect functionality."""

    @patch("boto3.client")
    @patch("boto3.resource")
    def test_successful_connection_instruments_stack(self, mock_boto3_resource, mock_boto3_client):
        """Test that successful connection updates session and instruments stack."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.get_item.return_value = {"Item": {"SessionId": "test-session-id", "StackName": "test-stack"}}
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        # Mock CloudFormation and Lambda clients
        mock_cf_client = Mock()
        mock_lambda_client = Mock()

        # Mock stack outputs to include layer ARN
        mock_cf_client.describe_stacks.return_value = {
            "Stacks": [{"Outputs": [{"OutputKey": "DebuggerLayerArn", "OutputValue": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"}]}]
        }

        # Mock stack resources
        mock_cf_client.list_stack_resources.return_value = {
            "StackResourceSummaries": [
                {"ResourceType": "AWS::Lambda::Function", "PhysicalResourceId": "test-function-1", "LogicalResourceId": "Function1"},
                {"ResourceType": "AWS::Lambda::Function", "PhysicalResourceId": "test-function-2", "LogicalResourceId": "Function2"},
                {"ResourceType": "AWS::S3::Bucket", "PhysicalResourceId": "test-bucket", "LogicalResourceId": "Bucket1"},
            ]
        }

        # Mock Lambda function configurations
        mock_lambda_client.get_function_configuration.side_effect = [
            {"Environment": {"Variables": {"EXISTING_VAR": "value"}}, "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:OtherLayer:1"}]},
            {"Environment": {"Variables": {}}, "Layers": []},
        ]

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            elif service_name == "lambda":
                return mock_lambda_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        event = {"requestContext": {"connectionId": "test-connection-id", "authorizer": {"sessionId": "test-session-id"}}}

        result = lambda_handler(event, None)

        # Verify DynamoDB operations
        mock_table.get_item.assert_called_once_with(Key={"SessionId": "test-session-id"})
        mock_table.update_item.assert_called_once_with(
            Key={"SessionId": "test-session-id"},
            UpdateExpression="SET #status = :status, ConnectionId = :conn_id",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "ACTIVE", ":conn_id": "test-connection-id"},
        )

        # Verify Lambda instrumentation
        assert mock_lambda_client.update_function_configuration.call_count == 2

        # Check first function update
        first_call = mock_lambda_client.update_function_configuration.call_args_list[0]
        assert first_call[1]["FunctionName"] == "test-function-1"
        assert first_call[1]["Environment"]["Variables"]["DEBUGGER_SESSION_ID"] == "test-session-id"
        assert first_call[1]["Environment"]["Variables"]["DEBUGGER_CONNECTION_ID"] == "test-connection-id"
        assert first_call[1]["Environment"]["Variables"]["AWS_LAMBDA_EXEC_WRAPPER"] == "/opt/bin/bootstrap"
        assert first_call[1]["Environment"]["Variables"]["EXISTING_VAR"] == "value"
        assert len(first_call[1]["Layers"]) == 2  # Original layer + debug layer

        # Check second function update
        second_call = mock_lambda_client.update_function_configuration.call_args_list[1]
        assert second_call[1]["FunctionName"] == "test-function-2"
        assert len(second_call[1]["Layers"]) == 1  # Only debug layer

        # Verify response
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Connected"
        assert body["sessionId"] == "test-session-id"

    @patch("boto3.resource")
    def test_missing_session_id_returns_403(self, mock_boto3_resource):
        """Test that missing sessionId returns 403 Forbidden."""
        event = {
            "requestContext": {
                "connectionId": "test-connection-id",
                "authorizer": {},  # No sessionId
            }
        }

        result = lambda_handler(event, None)

        assert result["statusCode"] == 403
        body = json.loads(result["body"])
        assert body["error"] == "No session ID found"

    @patch("boto3.resource")
    def test_missing_authorizer_context_returns_403(self, mock_boto3_resource):
        """Test that missing authorizer context returns 403 Forbidden."""
        event = {
            "requestContext": {
                "connectionId": "test-connection-id"
                # No authorizer key
            }
        }

        result = lambda_handler(event, None)

        assert result["statusCode"] == 403
        body = json.loads(result["body"])
        assert body["error"] == "No session ID found"

    @patch("boto3.resource")
    def test_session_not_found_returns_404(self, mock_boto3_resource):
        """Test that non-existent session returns 404."""
        mock_table = Mock()
        mock_table.get_item.return_value = {}  # No Item key
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"requestContext": {"connectionId": "test-connection-id", "authorizer": {"sessionId": "non-existent-session"}}}

        result = lambda_handler(event, None)

        assert result["statusCode"] == 404
        body = json.loads(result["body"])
        assert body["error"] == "Session not found"

    @patch("boto3.resource")
    def test_missing_stack_name_returns_400(self, mock_boto3_resource):
        """Test that session without stack name returns 400."""
        mock_table = Mock()
        mock_table.get_item.return_value = {
            "Item": {"SessionId": "test-session-id"}  # No StackName
        }
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"requestContext": {"connectionId": "test-connection-id", "authorizer": {"sessionId": "test-session-id"}}}

        result = lambda_handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error"] == "No stack name in session"

    @patch("boto3.client")
    @patch("boto3.resource")
    def test_instrumentation_continues_on_function_error(self, mock_boto3_resource, mock_boto3_client):
        """Test that instrumentation continues even if one function fails."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.get_item.return_value = {"Item": {"SessionId": "test-session-id", "StackName": "test-stack"}}
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        # Mock CloudFormation and Lambda clients
        mock_cf_client = Mock()
        mock_lambda_client = Mock()

        # Mock stack outputs
        mock_cf_client.describe_stacks.return_value = {
            "Stacks": [{"Outputs": [{"OutputKey": "DebuggerLayerArn", "OutputValue": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"}]}]
        }

        # Mock stack resources
        mock_cf_client.list_stack_resources.return_value = {
            "StackResourceSummaries": [
                {"ResourceType": "AWS::Lambda::Function", "PhysicalResourceId": "test-function-1", "LogicalResourceId": "Function1"},
                {"ResourceType": "AWS::Lambda::Function", "PhysicalResourceId": "test-function-2", "LogicalResourceId": "Function2"},
            ]
        }

        # First function fails, second succeeds
        mock_lambda_client.get_function_configuration.side_effect = [Exception("Function not found"), {"Environment": {"Variables": {}}, "Layers": []}]

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            elif service_name == "lambda":
                return mock_lambda_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        event = {"requestContext": {"connectionId": "test-connection-id", "authorizer": {"sessionId": "test-session-id"}}}

        result = lambda_handler(event, None)

        # Should still succeed overall
        assert result["statusCode"] == 200

        # Second function should still be updated
        assert mock_lambda_client.update_function_configuration.call_count == 1
        assert mock_lambda_client.update_function_configuration.call_args[1]["FunctionName"] == "test-function-2"

    @patch("boto3.client")
    @patch("boto3.resource")
    def test_missing_layer_arn_continues_without_instrumentation(self, mock_boto3_resource, mock_boto3_client):
        """Test that missing layer ARN logs error but continues."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.get_item.return_value = {"Item": {"SessionId": "test-session-id", "StackName": "test-stack"}}
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        # Mock CloudFormation client
        mock_cf_client = Mock()

        # Mock stack outputs without layer ARN
        mock_cf_client.describe_stacks.return_value = {"Stacks": [{"Outputs": [{"OutputKey": "SomeOtherOutput", "OutputValue": "some-value"}]}]}

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        event = {"requestContext": {"connectionId": "test-connection-id", "authorizer": {"sessionId": "test-session-id"}}}

        result = lambda_handler(event, None)

        # Should still succeed, just without instrumentation
        assert result["statusCode"] == 200


class TestInstrumentLambdaFunctions:
    """Test instrument_lambda_functions function."""

    @patch("boto3.client")
    def test_instrument_with_environment_variable(self, mock_boto3_client):
        """Test instrumentation with environment variable for stack name."""
        mock_cf_client = Mock()
        mock_lambda_client = Mock()

        # Mock stack outputs
        mock_cf_client.describe_stacks.return_value = {
            "Stacks": [{"Outputs": [{"OutputKey": "DebuggerLayerArn", "OutputValue": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"}]}]
        }

        # Mock stack resources
        mock_cf_client.list_stack_resources.return_value = {
            "StackResourceSummaries": [{"ResourceType": "AWS::Lambda::Function", "PhysicalResourceId": "test-function", "LogicalResourceId": "TestFunction"}]
        }

        # Mock function configuration
        mock_lambda_client.get_function_configuration.return_value = {"Environment": {"Variables": {}}, "Layers": []}

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            elif service_name == "lambda":
                return mock_lambda_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        # Set environment variable
        import os

        os.environ["AWS_CLOUDFORMATION_STACK_NAME"] = "my-plldb-stack"

        try:
            instrument_lambda_functions("target-stack", "session-123", "connection-456")

            # Verify it used the environment variable
            mock_cf_client.describe_stacks.assert_called_once_with(StackName="my-plldb-stack")
        finally:
            # Clean up
            os.environ.pop("AWS_CLOUDFORMATION_STACK_NAME", None)

    @patch("boto3.client")
    def test_layer_already_present_not_duplicated(self, mock_boto3_client):
        """Test that layer is not duplicated if already present."""
        mock_cf_client = Mock()
        mock_lambda_client = Mock()

        layer_arn = "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"

        # Mock stack outputs
        mock_cf_client.describe_stacks.return_value = {"Stacks": [{"Outputs": [{"OutputKey": "DebuggerLayerArn", "OutputValue": layer_arn}]}]}

        # Mock stack resources
        mock_cf_client.list_stack_resources.return_value = {
            "StackResourceSummaries": [{"ResourceType": "AWS::Lambda::Function", "PhysicalResourceId": "test-function", "LogicalResourceId": "TestFunction"}]
        }

        # Function already has the debug layer
        mock_lambda_client.get_function_configuration.return_value = {"Environment": {"Variables": {}}, "Layers": [{"Arn": layer_arn}]}

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            elif service_name == "lambda":
                return mock_lambda_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        instrument_lambda_functions("target-stack", "session-123", "connection-456")

        # Verify update was called
        mock_lambda_client.update_function_configuration.assert_called_once()
        call_args = mock_lambda_client.update_function_configuration.call_args[1]

        # Should still have only one instance of the layer
        assert len(call_args["Layers"]) == 1
        assert call_args["Layers"][0] == layer_arn
