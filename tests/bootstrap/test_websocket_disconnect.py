"""Tests for WebSocket disconnect Lambda function."""

import json
import pytest
from unittest.mock import Mock, patch
from plldb.bootstrap.cloudformation.lambda_functions.websocket_disconnect import lambda_handler


class TestWebSocketDisconnect:
    """Test WebSocket disconnect functionality."""

    @patch("boto3.resource")
    def test_successful_disconnection_updates_session(self, mock_boto3_resource):
        """Test that successful disconnection updates session to DISCONNECTED."""
        mock_table = Mock()
        mock_table.scan.return_value = {"Items": [{"SessionId": "test-session-id", "ConnectionId": "test-connection-id", "Status": "ACTIVE"}]}
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        # Verify scan was called correctly
        mock_table.scan.assert_called_once_with(FilterExpression="ConnectionId = :conn_id", ExpressionAttributeValues={":conn_id": "test-connection-id"})

        # Verify update was called correctly
        mock_table.update_item.assert_called_once_with(
            Key={"SessionId": "test-session-id"}, UpdateExpression="SET #status = :status", ExpressionAttributeNames={"#status": "Status"}, ExpressionAttributeValues={":status": "DISCONNECTED"}
        )

        # Verify response
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Disconnected"

    @patch("boto3.resource")
    def test_no_matching_session_still_returns_success(self, mock_boto3_resource):
        """Test that no matching session still returns success (idempotent)."""
        mock_table = Mock()
        mock_table.scan.return_value = {
            "Items": []  # No matching sessions
        }
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        # Verify scan was called but update was not
        mock_table.scan.assert_called_once()
        mock_table.update_item.assert_not_called()

        # Should still return success
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Disconnected"

    @patch("boto3.resource")
    def test_multiple_matching_sessions_updates_first(self, mock_boto3_resource):
        """Test that multiple matching sessions only updates the first one."""
        mock_table = Mock()
        mock_table.scan.return_value = {
            "Items": [
                {"SessionId": "test-session-id-1", "ConnectionId": "test-connection-id", "Status": "ACTIVE"},
                {"SessionId": "test-session-id-2", "ConnectionId": "test-connection-id", "Status": "ACTIVE"},
            ]
        }
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        # Should only update the first session
        mock_table.update_item.assert_called_once_with(
            Key={"SessionId": "test-session-id-1"}, UpdateExpression="SET #status = :status", ExpressionAttributeNames={"#status": "Status"}, ExpressionAttributeValues={":status": "DISCONNECTED"}
        )

        assert result["statusCode"] == 200

    @patch("boto3.resource")
    def test_scan_error_returns_500(self, mock_boto3_resource):
        """Test that scan errors return 500 Internal Server Error."""
        mock_table = Mock()
        mock_table.scan.side_effect = Exception("DynamoDB scan error")
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "DynamoDB scan error" in body["error"]

    @patch("boto3.resource")
    def test_update_error_returns_500(self, mock_boto3_resource):
        """Test that update errors return 500 Internal Server Error."""
        mock_table = Mock()
        mock_table.scan.return_value = {"Items": [{"SessionId": "test-session-id", "ConnectionId": "test-connection-id", "Status": "ACTIVE"}]}
        mock_table.update_item.side_effect = Exception("DynamoDB update error")
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"requestContext": {"connectionId": "test-connection-id"}}

        result = lambda_handler(event, None)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "DynamoDB update error" in body["error"]
