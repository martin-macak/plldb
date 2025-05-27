"""Tests for WebSocket connect Lambda function."""

import json
import pytest
from unittest.mock import Mock, patch
from plldb.bootstrap.cloudformation.lambda_functions.websocket_connect import lambda_handler


class TestWebSocketConnect:
    """Test WebSocket connect functionality."""

    @patch("boto3.resource")
    def test_successful_connection_updates_session(self, mock_boto3_resource):
        """Test that successful connection updates session to ACTIVE."""
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb
        
        event = {
            "requestContext": {
                "connectionId": "test-connection-id",
                "authorizer": {
                    "sessionId": "test-session-id"
                }
            }
        }
        
        result = lambda_handler(event, None)
        
        # Verify DynamoDB update was called correctly
        mock_table.update_item.assert_called_once_with(
            Key={"SessionId": "test-session-id"},
            UpdateExpression="SET #status = :status, ConnectionId = :conn_id",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":status": "ACTIVE",
                ":conn_id": "test-connection-id"
            }
        )
        
        # Verify response
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Connected"
        assert body["sessionId"] == "test-session-id"

    def test_missing_session_id_returns_403(self):
        """Test that missing sessionId returns 403 Forbidden."""
        event = {
            "requestContext": {
                "connectionId": "test-connection-id",
                "authorizer": {}  # No sessionId
            }
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 403
        body = json.loads(result["body"])
        assert body["error"] == "No session ID found"

    def test_missing_authorizer_context_returns_403(self):
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
    def test_dynamodb_error_returns_500(self, mock_boto3_resource):
        """Test that DynamoDB errors return 500 Internal Server Error."""
        mock_table = Mock()
        mock_table.update_item.side_effect = Exception("DynamoDB error")
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb
        
        event = {
            "requestContext": {
                "connectionId": "test-connection-id",
                "authorizer": {
                    "sessionId": "test-session-id"
                }
            }
        }
        
        result = lambda_handler(event, None)
        
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "DynamoDB error" in body["error"]

    @patch("boto3.resource")
    def test_connection_id_properly_extracted(self, mock_boto3_resource):
        """Test that connection ID is properly extracted from event."""
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb
        
        connection_id = "unique-connection-id-12345"
        event = {
            "requestContext": {
                "connectionId": connection_id,
                "authorizer": {
                    "sessionId": "test-session-id"
                }
            }
        }
        
        lambda_handler(event, None)
        
        # Verify the correct connection ID was used in the update
        update_call = mock_table.update_item.call_args
        assert update_call[1]["ExpressionAttributeValues"][":conn_id"] == connection_id