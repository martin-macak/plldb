"""Tests for WebSocket disconnect Lambda function."""

import json
from unittest.mock import Mock, patch
from plldb.cloudformation.lambda_functions.websocket_disconnect import lambda_handler, invoke_instrumentation_lambda


class TestWebSocketDisconnect:
    """Test WebSocket disconnect functionality."""

    @patch("boto3.client")
    @patch("boto3.resource")
    def test_successful_disconnection_invokes_uninstrumentation_lambda(self, mock_boto3_resource, mock_boto3_client):
        """Test that successful disconnection updates session and invokes uninstrumentation lambda."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.scan.return_value = {"Items": [{"SessionId": "test-session-id", "StackName": "test-stack", "ConnectionId": "test-connection-id"}]}
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        # Mock Lambda client
        mock_lambda_client = Mock()
        mock_lambda_client.invoke.return_value = {"StatusCode": 202}
        mock_boto3_client.return_value = mock_lambda_client

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        # Verify DynamoDB operations
        mock_table.scan.assert_called_once_with(FilterExpression="ConnectionId = :conn_id", ExpressionAttributeValues={":conn_id": "test-connection-id"})
        mock_table.update_item.assert_called_once_with(
            Key={"SessionId": "test-session-id"},
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "DISCONNECTED"},
        )

        # Verify Lambda invocation
        mock_lambda_client.invoke.assert_called_once_with(
            FunctionName="plldb-debugger-instrumentation", InvocationType="Event", Payload=json.dumps({"command": "uninstrument", "stackName": "test-stack"})
        )

        # Verify response
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Disconnected"

    @patch("boto3.client")
    @patch("boto3.resource")
    def test_no_matching_session_still_returns_200(self, mock_boto3_resource, mock_boto3_client):
        """Test that disconnection with no matching session still returns 200."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.scan.return_value = {"Items": []}  # No matching session
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        # Verify DynamoDB scan was called
        mock_table.scan.assert_called_once()

        # Should not attempt to update or invoke lambda
        mock_table.update_item.assert_not_called()

        # Verify response
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Disconnected"

    @patch("boto3.client")
    @patch("boto3.resource")
    def test_session_without_stack_name_skips_uninstrumentation(self, mock_boto3_resource, mock_boto3_client):
        """Test that session without stack name skips uninstrumentation."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.scan.return_value = {"Items": [{"SessionId": "test-session-id", "ConnectionId": "test-connection-id"}]}  # No StackName
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        # Mock Lambda client
        mock_lambda_client = Mock()
        mock_boto3_client.return_value = mock_lambda_client

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        # Verify session was updated but lambda was not invoked
        mock_table.update_item.assert_called_once()
        mock_lambda_client.invoke.assert_not_called()

        # Verify response
        assert result["statusCode"] == 200

    @patch("boto3.client")
    @patch("boto3.resource")
    def test_uninstrumentation_lambda_invocation_failure(self, mock_boto3_resource, mock_boto3_client):
        """Test handling of uninstrumentation lambda invocation failure."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.scan.return_value = {"Items": [{"SessionId": "test-session-id", "StackName": "test-stack", "ConnectionId": "test-connection-id"}]}
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        # Mock Lambda client to raise exception
        mock_lambda_client = Mock()
        mock_lambda_client.invoke.side_effect = Exception("Lambda invocation failed")
        mock_boto3_client.return_value = mock_lambda_client

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        # Should not raise exception, just log it
        result = lambda_handler(event, None)

        # Disconnection should still succeed even if uninstrumentation fails
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Disconnected"

    @patch("boto3.resource")
    def test_exception_returns_500(self, mock_boto3_resource):
        """Test that exceptions return 500 Internal Server Error."""
        # Mock DynamoDB to raise an exception
        mock_boto3_resource.side_effect = Exception("DynamoDB error")

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "DynamoDB error" in body["error"]


class TestInvokeInstrumentationLambda:
    """Test invoke_instrumentation_lambda function."""

    @patch("boto3.client")
    def test_invoke_uninstrumentation_lambda_success(self, mock_boto3_client):
        """Test successful uninstrumentation lambda invocation."""
        mock_lambda_client = Mock()
        mock_lambda_client.invoke.return_value = {"StatusCode": 202}
        mock_boto3_client.return_value = mock_lambda_client

        invoke_instrumentation_lambda("uninstrument", "test-stack")

        mock_lambda_client.invoke.assert_called_once_with(
            FunctionName="plldb-debugger-instrumentation", InvocationType="Event", Payload=json.dumps({"command": "uninstrument", "stackName": "test-stack"})
        )

    @patch("boto3.client")
    def test_invoke_uninstrumentation_lambda_exception(self, mock_boto3_client):
        """Test uninstrumentation lambda invocation exception handling."""
        mock_lambda_client = Mock()
        mock_lambda_client.invoke.side_effect = Exception("Invocation failed")
        mock_boto3_client.return_value = mock_lambda_client

        # Should not raise exception
        invoke_instrumentation_lambda("uninstrument", "test-stack")

        # Verify invocation was attempted
        mock_lambda_client.invoke.assert_called_once()
