"""Tests for WebSocket connect Lambda function."""

import json
from unittest.mock import Mock, patch
from plldb.cloudformation.lambda_functions.websocket_connect import lambda_handler, invoke_instrumentation_lambda


class TestWebSocketConnect:
    """Test WebSocket connect functionality."""

    @patch("boto3.client")
    @patch("boto3.resource")
    def test_successful_connection_invokes_instrumentation_lambda(self, mock_boto3_resource, mock_boto3_client):
        """Test that successful connection updates session and invokes instrumentation lambda."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.get_item.return_value = {"Item": {"SessionId": "test-session-id", "StackName": "test-stack"}}
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        # Mock Lambda client
        mock_lambda_client = Mock()
        mock_lambda_client.invoke.return_value = {"StatusCode": 202}

        mock_boto3_client.return_value = mock_lambda_client

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

        # Verify Lambda invocation
        mock_lambda_client.invoke.assert_called_once_with(
            FunctionName="plldb-debugger-instrumentation",
            InvocationType="Event",
            Payload=json.dumps({"command": "instrument", "stackName": "test-stack", "sessionId": "test-session-id", "connectionId": "test-connection-id"}),
        )

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
                "connectionId": "test-connection-id",
                # No authorizer key
            }
        }

        result = lambda_handler(event, None)

        assert result["statusCode"] == 403
        body = json.loads(result["body"])
        assert body["error"] == "No session ID found"

    @patch("boto3.resource")
    def test_session_not_found_returns_404(self, mock_boto3_resource):
        """Test that non-existent session returns 404 Not Found."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.get_item.return_value = {}  # No Item key
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"requestContext": {"connectionId": "test-connection-id", "authorizer": {"sessionId": "nonexistent-session-id"}}}

        result = lambda_handler(event, None)

        assert result["statusCode"] == 404
        body = json.loads(result["body"])
        assert body["error"] == "Session not found"

    @patch("boto3.resource")
    def test_missing_stack_name_returns_400(self, mock_boto3_resource):
        """Test that session without stack name returns 400 Bad Request."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.get_item.return_value = {"Item": {"SessionId": "test-session-id"}}  # No StackName
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
    def test_instrumentation_lambda_invocation_failure(self, mock_boto3_resource, mock_boto3_client):
        """Test handling of instrumentation lambda invocation failure."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.get_item.return_value = {"Item": {"SessionId": "test-session-id", "StackName": "test-stack"}}
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        # Mock Lambda client to raise exception
        mock_lambda_client = Mock()
        mock_lambda_client.invoke.side_effect = Exception("Lambda invocation failed")
        mock_boto3_client.return_value = mock_lambda_client

        event = {"requestContext": {"connectionId": "test-connection-id", "authorizer": {"sessionId": "test-session-id"}}}

        # Should not raise exception, just log it
        result = lambda_handler(event, None)

        # Connection should still succeed even if instrumentation fails
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Connected"

    @patch("boto3.resource")
    def test_exception_returns_500(self, mock_boto3_resource):
        """Test that exceptions return 500 Internal Server Error."""
        # Mock DynamoDB to raise an exception
        mock_boto3_resource.side_effect = Exception("DynamoDB error")

        event = {"requestContext": {"connectionId": "test-connection-id", "authorizer": {"sessionId": "test-session-id"}}}

        result = lambda_handler(event, None)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "DynamoDB error" in body["error"]


class TestInvokeInstrumentationLambda:
    """Test invoke_instrumentation_lambda function."""

    @patch("boto3.client")
    def test_invoke_instrumentation_lambda_success(self, mock_boto3_client):
        """Test successful lambda invocation."""
        mock_lambda_client = Mock()
        mock_lambda_client.invoke.return_value = {"StatusCode": 202}
        mock_boto3_client.return_value = mock_lambda_client

        invoke_instrumentation_lambda("instrument", "test-stack", "session-123", "connection-456")

        mock_lambda_client.invoke.assert_called_once_with(
            FunctionName="plldb-debugger-instrumentation",
            InvocationType="Event",
            Payload=json.dumps({"command": "instrument", "stackName": "test-stack", "sessionId": "session-123", "connectionId": "connection-456"}),
        )

    @patch("boto3.client")
    def test_invoke_instrumentation_lambda_without_optional_params(self, mock_boto3_client):
        """Test lambda invocation without optional parameters."""
        mock_lambda_client = Mock()
        mock_lambda_client.invoke.return_value = {"StatusCode": 202}
        mock_boto3_client.return_value = mock_lambda_client

        invoke_instrumentation_lambda("uninstrument", "test-stack")

        mock_lambda_client.invoke.assert_called_once_with(
            FunctionName="plldb-debugger-instrumentation", InvocationType="Event", Payload=json.dumps({"command": "uninstrument", "stackName": "test-stack"})
        )

    @patch("boto3.client")
    def test_invoke_instrumentation_lambda_exception(self, mock_boto3_client):
        """Test lambda invocation exception handling."""
        mock_lambda_client = Mock()
        mock_lambda_client.invoke.side_effect = Exception("Invocation failed")
        mock_boto3_client.return_value = mock_lambda_client

        # Should not raise exception
        invoke_instrumentation_lambda("instrument", "test-stack", "session-123", "connection-456")

        # Verify invocation was attempted
        mock_lambda_client.invoke.assert_called_once()
