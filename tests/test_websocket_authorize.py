"""Tests for WebSocket authorization Lambda function."""

import pytest
from unittest.mock import Mock, patch
from plldb.cloudformation.lambda_functions.websocket_authorize import lambda_handler, generate_policy


class TestWebSocketAuthorize:
    """Test WebSocket authorization functionality."""

    def test_missing_session_id_denies_access(self):
        """Test that missing sessionId in query params denies access."""
        event = {"methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/*/GET/", "queryStringParameters": None}

        result = lambda_handler(event, None)

        assert result["principalId"] == "user"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_empty_query_params_denies_access(self):
        """Test that empty query params denies access."""
        event = {"methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/*/GET/", "queryStringParameters": {}}

        result = lambda_handler(event, None)

        assert result["principalId"] == "user"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    @patch("boto3.resource")
    def test_nonexistent_session_denies_access(self, mock_boto3_resource):
        """Test that non-existent session denies access."""
        mock_table = Mock()
        mock_table.get_item.return_value = {}  # No Item key means session doesn't exist
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/*/GET/", "queryStringParameters": {"sessionId": "test-session-id"}}

        result = lambda_handler(event, None)

        mock_table.get_item.assert_called_once_with(Key={"SessionId": "test-session-id"})
        assert result["principalId"] == "user"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    @patch("boto3.resource")
    def test_non_pending_session_denies_access(self, mock_boto3_resource):
        """Test that non-PENDING session status denies access."""
        mock_table = Mock()
        mock_table.get_item.return_value = {
            "Item": {
                "SessionId": "test-session-id",
                "Status": "ACTIVE",  # Not PENDING
            }
        }
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/*/GET/", "queryStringParameters": {"sessionId": "test-session-id"}}

        result = lambda_handler(event, None)

        assert result["principalId"] == "user"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    @patch("boto3.resource")
    def test_pending_session_allows_access(self, mock_boto3_resource):
        """Test that PENDING session allows access and includes sessionId in context."""
        mock_table = Mock()
        mock_table.get_item.return_value = {"Item": {"SessionId": "test-session-id", "Status": "PENDING"}}
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/*/GET/", "queryStringParameters": {"sessionId": "test-session-id"}}

        result = lambda_handler(event, None)

        assert result["principalId"] == "user"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        assert "context" in result
        assert result["context"]["sessionId"] == "test-session-id"

    @patch("boto3.resource")
    def test_dynamodb_error_denies_access(self, mock_boto3_resource):
        """Test that DynamoDB errors result in denied access."""
        mock_table = Mock()
        mock_table.get_item.side_effect = Exception("DynamoDB error")
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3_resource.return_value = mock_dynamodb

        event = {"methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/*/GET/", "queryStringParameters": {"sessionId": "test-session-id"}}

        result = lambda_handler(event, None)

        assert result["principalId"] == "user"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_generate_policy(self):
        """Test IAM policy generation."""
        resource = "arn:aws:execute-api:us-east-1:123456789012:abcdef123/*/GET/"

        # Test Allow policy
        allow_policy = generate_policy("user123", "Allow", resource)
        assert allow_policy["principalId"] == "user123"
        assert allow_policy["policyDocument"]["Version"] == "2012-10-17"
        assert allow_policy["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        assert allow_policy["policyDocument"]["Statement"][0]["Action"] == "execute-api:Invoke"
        assert allow_policy["policyDocument"]["Statement"][0]["Resource"] == resource

        # Test Deny policy
        deny_policy = generate_policy("user456", "Deny", resource)
        assert deny_policy["principalId"] == "user456"
        assert deny_policy["policyDocument"]["Statement"][0]["Effect"] == "Deny"
