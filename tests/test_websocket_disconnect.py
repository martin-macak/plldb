"""Tests for WebSocket disconnect Lambda function."""

import json
from unittest.mock import Mock, patch
from plldb.cloudformation.lambda_functions.websocket_disconnect import lambda_handler, deinstrument_lambda_functions


class TestWebSocketDisconnect:
    """Test WebSocket disconnect functionality."""

    @patch("boto3.client")
    @patch("boto3.resource")
    def test_successful_disconnection_deinstruments_stack(self, mock_boto3_resource, mock_boto3_client):
        """Test that successful disconnection updates session and de-instruments stack."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.scan.return_value = {"Items": [{"SessionId": "test-session-id", "StackName": "test-stack", "ConnectionId": "test-connection-id"}]}
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
            ]
        }

        # Mock Lambda function configurations - with debug settings that need to be removed
        mock_lambda_client.get_function_configuration.side_effect = [
            {
                "Environment": {
                    "Variables": {
                        "EXISTING_VAR": "value",
                        "DEBUGGER_SESSION_ID": "test-session-id",
                        "DEBUGGER_CONNECTION_ID": "test-connection-id",
                        "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bin/bootstrap",
                    }
                },
                "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"}, {"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:OtherLayer:1"}],
            },
            {
                "Environment": {"Variables": {"DEBUGGER_SESSION_ID": "test-session-id", "DEBUGGER_CONNECTION_ID": "test-connection-id", "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bin/bootstrap"}},
                "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"}],
            },
        ]

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            elif service_name == "lambda":
                return mock_lambda_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        # Verify DynamoDB operations
        mock_table.scan.assert_called_once_with(FilterExpression="ConnectionId = :conn_id", ExpressionAttributeValues={":conn_id": "test-connection-id"})
        mock_table.update_item.assert_called_once_with(
            Key={"SessionId": "test-session-id"}, UpdateExpression="SET #status = :status", ExpressionAttributeNames={"#status": "Status"}, ExpressionAttributeValues={":status": "DISCONNECTED"}
        )

        # Verify Lambda de-instrumentation
        assert mock_lambda_client.update_function_configuration.call_count == 2

        # Check first function update - should keep existing vars but remove debug ones
        first_call = mock_lambda_client.update_function_configuration.call_args_list[0]
        assert first_call[1]["FunctionName"] == "test-function-1"
        assert first_call[1]["Environment"]["Variables"] == {"EXISTING_VAR": "value"}
        assert len(first_call[1]["Layers"]) == 1  # Only OtherLayer remains
        assert first_call[1]["Layers"][0] == "arn:aws:lambda:us-east-1:123456789012:layer:OtherLayer:1"

        # Check second function update - should have empty vars and no layers
        second_call = mock_lambda_client.update_function_configuration.call_args_list[1]
        assert second_call[1]["FunctionName"] == "test-function-2"
        assert second_call[1]["Environment"] == {}  # Empty dict (no Variables key when empty)
        assert second_call[1]["Layers"] == []  # Empty list

        # Verify response
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Disconnected"

    @patch("boto3.resource")
    def test_no_session_found_still_returns_success(self, mock_boto3_resource):
        """Test that disconnection succeeds even if no session found."""
        mock_table = Mock()
        mock_table.scan.return_value = {"Items": []}  # No items found
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        # Should still return success
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Disconnected"

        # No update should be called
        mock_table.update_item.assert_not_called()

    @patch("boto3.resource")
    def test_dynamodb_error_returns_500(self, mock_boto3_resource):
        """Test that DynamoDB errors return 500 Internal Server Error."""
        mock_table = Mock()
        mock_table.scan.side_effect = Exception("DynamoDB error")
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "DynamoDB error" in body["error"]

    @patch("boto3.client")
    @patch("boto3.resource")
    def test_no_stack_name_skips_deinstrumentation(self, mock_boto3_resource, mock_boto3_client):
        """Test that missing stack name skips de-instrumentation."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.scan.return_value = {
            "Items": [{"SessionId": "test-session-id", "ConnectionId": "test-connection-id"}]  # No StackName
        }
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        # Mock clients
        mock_cf_client = Mock()
        mock_lambda_client = Mock()

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            elif service_name == "lambda":
                return mock_lambda_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        # Should succeed without calling CloudFormation
        assert result["statusCode"] == 200
        mock_cf_client.describe_stacks.assert_not_called()
        mock_cf_client.list_stack_resources.assert_not_called()
        mock_lambda_client.update_function_configuration.assert_not_called()

    @patch("boto3.client")
    @patch("boto3.resource")
    def test_deinstrumentation_continues_on_function_error(self, mock_boto3_resource, mock_boto3_client):
        """Test that de-instrumentation continues even if one function fails."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.scan.return_value = {"Items": [{"SessionId": "test-session-id", "StackName": "test-stack", "ConnectionId": "test-connection-id"}]}
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
        mock_lambda_client.get_function_configuration.side_effect = [Exception("Function not found"), {"Environment": {"Variables": {"DEBUGGER_SESSION_ID": "test"}}, "Layers": []}]

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            elif service_name == "lambda":
                return mock_lambda_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        # Should still succeed overall
        assert result["statusCode"] == 200

        # Second function should still be updated
        assert mock_lambda_client.update_function_configuration.call_count == 1
        assert mock_lambda_client.update_function_configuration.call_args[1]["FunctionName"] == "test-function-2"


class TestDeinstrumentLambdaFunctions:
    """Test deinstrument_lambda_functions function."""

    @patch("boto3.client")
    def test_deinstrument_removes_only_debug_variables(self, mock_boto3_client):
        """Test that de-instrumentation removes only debug environment variables."""
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

        # Mock function configuration with both debug and regular vars
        mock_lambda_client.get_function_configuration.return_value = {
            "Environment": {
                "Variables": {
                    "REGULAR_VAR": "keep-this",
                    "ANOTHER_VAR": "also-keep",
                    "DEBUGGER_SESSION_ID": "remove-this",
                    "DEBUGGER_CONNECTION_ID": "remove-this-too",
                    "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bin/bootstrap",
                }
            },
            "Layers": [],
        }

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            elif service_name == "lambda":
                return mock_lambda_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        deinstrument_lambda_functions("target-stack")

        # Verify update was called
        mock_lambda_client.update_function_configuration.assert_called_once()
        call_args = mock_lambda_client.update_function_configuration.call_args[1]

        # Should keep only regular vars
        assert call_args["Environment"]["Variables"] == {"REGULAR_VAR": "keep-this", "ANOTHER_VAR": "also-keep"}

    @patch("boto3.client")
    def test_deinstrument_handles_empty_environment(self, mock_boto3_client):
        """Test that de-instrumentation handles functions with no environment variables."""
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

        # Function has no environment block
        mock_lambda_client.get_function_configuration.return_value = {"Layers": []}

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            elif service_name == "lambda":
                return mock_lambda_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        # Should not raise an error
        deinstrument_lambda_functions("target-stack")

        # Verify update was called with empty dict
        mock_lambda_client.update_function_configuration.assert_called_once()
        call_args = mock_lambda_client.update_function_configuration.call_args[1]
        assert call_args["Environment"] == {}

    @patch("boto3.client")
    def test_deinstrument_removes_only_debug_layer(self, mock_boto3_client):
        """Test that de-instrumentation removes only the debug layer."""
        mock_cf_client = Mock()
        mock_lambda_client = Mock()

        debug_layer_arn = "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"
        other_layer_arn = "arn:aws:lambda:us-east-1:123456789012:layer:OtherLayer:2"

        # Mock stack outputs
        mock_cf_client.describe_stacks.return_value = {"Stacks": [{"Outputs": [{"OutputKey": "DebuggerLayerArn", "OutputValue": debug_layer_arn}]}]}

        # Mock stack resources
        mock_cf_client.list_stack_resources.return_value = {
            "StackResourceSummaries": [{"ResourceType": "AWS::Lambda::Function", "PhysicalResourceId": "test-function", "LogicalResourceId": "TestFunction"}]
        }

        # Function has multiple layers
        mock_lambda_client.get_function_configuration.return_value = {
            "Environment": {"Variables": {}},
            "Layers": [
                {"Arn": debug_layer_arn},
                {"Arn": other_layer_arn},
                {"Arn": debug_layer_arn},  # Duplicate to test deduplication
            ],
        }

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            elif service_name == "lambda":
                return mock_lambda_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        deinstrument_lambda_functions("target-stack")

        # Verify update was called
        mock_lambda_client.update_function_configuration.assert_called_once()
        call_args = mock_lambda_client.update_function_configuration.call_args[1]

        # Should keep only the other layer
        assert call_args["Layers"] == [other_layer_arn]

    @patch("boto3.client")
    def test_stack_resources_error_handled_gracefully(self, mock_boto3_client):
        """Test that errors listing stack resources are handled gracefully."""
        mock_cf_client = Mock()

        # Mock stack outputs
        mock_cf_client.describe_stacks.return_value = {
            "Stacks": [{"Outputs": [{"OutputKey": "DebuggerLayerArn", "OutputValue": "arn:aws:lambda:us-east-1:123456789012:layer:PLLDBDebuggerRuntime:1"}]}]
        }

        # list_stack_resources fails
        mock_cf_client.list_stack_resources.side_effect = Exception("Stack not found")

        def mock_client(service_name):
            if service_name == "cloudformation":
                return mock_cf_client
            return Mock()

        mock_boto3_client.side_effect = mock_client

        # Should not raise an error
        deinstrument_lambda_functions("non-existent-stack")
