import json
import os
import sys
import time
from unittest.mock import Mock, patch, MagicMock, mock_open
from typing import Any, Dict

import pytest
import boto3
from moto import mock_aws

# Import the module under test
from plldb.cloudformation.layer import lambda_runtime


class TestLambdaRuntimeUtilities:
    """Test utility functions in lambda_runtime module."""

    def test_get_lambda_runtime_api_present(self, monkeypatch):
        """Test getting Lambda Runtime API endpoint when set."""
        monkeypatch.setenv("AWS_LAMBDA_RUNTIME_API", "127.0.0.1:9001")
        result = lambda_runtime.get_lambda_runtime_api()
        assert result == "127.0.0.1:9001"

    def test_get_lambda_runtime_api_missing(self, monkeypatch):
        """Test getting Lambda Runtime API endpoint when not set."""
        monkeypatch.delenv("AWS_LAMBDA_RUNTIME_API", raising=False)
        result = lambda_runtime.get_lambda_runtime_api()
        assert result == ""

    @patch("urllib.request.urlopen")
    def test_get_next_invocation_success(self, mock_urlopen):
        """Test successful retrieval of next invocation."""
        # Mock response
        mock_response = Mock()
        mock_response.read.return_value = b'{"test": "event"}'
        mock_response.headers = {"Lambda-Runtime-Aws-Request-Id": "test-request-id"}
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        event, request_id = lambda_runtime.get_next_invocation("127.0.0.1:9001")

        assert event == {"test": "event"}
        assert request_id == "test-request-id"
        mock_urlopen.assert_called_once_with("http://127.0.0.1:9001/2018-06-01/runtime/invocation/next")

    @patch("urllib.request.urlopen")
    def test_get_next_invocation_error(self, mock_urlopen):
        """Test error handling in get_next_invocation."""
        mock_urlopen.side_effect = Exception("Connection error")

        with pytest.raises(Exception, match="Connection error"):
            lambda_runtime.get_next_invocation("127.0.0.1:9001")

    @patch("urllib.request.urlopen")
    def test_send_response_success(self, mock_urlopen):
        """Test successful response sending."""
        mock_response = Mock()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        lambda_runtime.send_response("127.0.0.1:9001", "test-request-id", {"result": "success"})

        # Verify URL and data
        args, kwargs = mock_urlopen.call_args
        request = args[0]
        assert request.get_full_url() == "http://127.0.0.1:9001/2018-06-01/runtime/invocation/test-request-id/response"
        assert request.data == b'{"result": "success"}'
        assert request.get_method() == "POST"

    @patch("urllib.request.urlopen")
    def test_send_response_error(self, mock_urlopen):
        """Test error handling in send_response."""
        mock_urlopen.side_effect = Exception("Network error")

        with pytest.raises(Exception, match="Network error"):
            lambda_runtime.send_response("127.0.0.1:9001", "test-request-id", {"result": "success"})

    @patch("urllib.request.urlopen")
    def test_send_error_success(self, mock_urlopen):
        """Test successful error response sending."""
        mock_response = Mock()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        lambda_runtime.send_error("127.0.0.1:9001", "test-request-id", "Test error", "TestException")

        # Verify URL and data
        args, kwargs = mock_urlopen.call_args
        request = args[0]
        assert request.get_full_url() == "http://127.0.0.1:9001/2018-06-01/runtime/invocation/test-request-id/error"
        data = json.loads(request.data.decode())
        assert data["errorMessage"] == "Test error"
        assert data["errorType"] == "TestException"

    @patch("urllib.request.urlopen")
    def test_send_error_default_type(self, mock_urlopen):
        """Test error response with default error type."""
        mock_response = Mock()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        lambda_runtime.send_error("127.0.0.1:9001", "test-request-id", "Test error")

        args, kwargs = mock_urlopen.call_args
        request = args[0]
        data = json.loads(request.data.decode())
        assert data["errorType"] == "Error"


class TestAWSInteractions:
    """Test AWS service interaction functions."""

    @mock_aws
    def test_assume_debugger_role_success(self, monkeypatch):
        """Test successful role assumption."""
        # Setup IAM role
        iam = boto3.client("iam")
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::123456789012:root"},
                    "Action": "sts:AssumeRole",
                    "Condition": {"StringEquals": {"sts:ExternalId": "plldb-debugger"}},
                }
            ],
        }
        iam.create_role(
            RoleName="PLLDBDebuggerRole",
            AssumeRolePolicyDocument=json.dumps(trust_policy),
        )

        # Test role assumption
        session = lambda_runtime.assume_debugger_role()

        assert isinstance(session, boto3.Session)
        # Verify session has credentials
        credentials = session.get_credentials()
        assert credentials is not None

    @mock_aws
    def test_create_debugger_request_success(self, mock_aws_session, monkeypatch):
        """Test successful creation of debugger request in DynamoDB."""
        # Setup environment
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "test-function")
        monkeypatch.setenv("TEST_VAR", "test-value")

        # Create DynamoDB table
        dynamodb = mock_aws_session.resource("dynamodb")
        dynamodb.create_table(
            TableName="PLLDBDebugger",
            KeySchema=[{"AttributeName": "RequestId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "RequestId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Test data
        event = {"test": "event"}
        context = {"aws_request_id": "test-request-id"}

        # Create request
        lambda_runtime.create_debugger_request(
            mock_aws_session,
            "test-request-id",
            "test-session-id",
            "test-connection-id",
            event,
            context,
        )

        # Verify item was created
        table = dynamodb.Table("PLLDBDebugger")
        response = table.get_item(Key={"RequestId": "test-request-id"})
        item = response["Item"]

        assert item["RequestId"] == "test-request-id"
        assert item["SessionId"] == "test-session-id"
        assert item["ConnectionId"] == "test-connection-id"
        assert json.loads(item["Request"]) == {"event": event, "context": context}
        assert item["EnvironmentVariables"]["TEST_VAR"] == "test-value"
        assert item["StatusCode"] == 0

    @mock_aws
    def test_create_debugger_request_error(self, mock_aws_session):
        """Test error handling in create_debugger_request."""
        # Don't create table, so put_item will fail
        with pytest.raises(Exception):
            lambda_runtime.create_debugger_request(
                mock_aws_session,
                "test-request-id",
                "test-session-id",
                "test-connection-id",
                {},
                {},
            )


class TestPollingAndWebSocket:
    """Test polling and WebSocket notification functions."""

    @mock_aws
    def test_poll_for_response_success(self, mock_aws_session):
        """Test successful polling for debugger response."""
        # Create DynamoDB table
        dynamodb = mock_aws_session.resource("dynamodb")
        table = dynamodb.create_table(
            TableName="PLLDBDebugger",
            KeySchema=[{"AttributeName": "RequestId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "RequestId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Put initial item
        table.put_item(Item={"RequestId": "test-request-id", "StatusCode": 0})

        # Update item to simulate debugger response
        table.update_item(
            Key={"RequestId": "test-request-id"},
            UpdateExpression="SET StatusCode = :status, #resp = :response",
            ExpressionAttributeNames={"#resp": "Response"},
            ExpressionAttributeValues={
                ":status": 200,
                ":response": json.dumps({"result": "success"}),
            },
        )

        # Poll for response
        response, error = lambda_runtime.poll_for_response(mock_aws_session, "test-request-id", timeout=1)

        assert response == {"result": "success"}
        assert error is None

    @mock_aws
    def test_poll_for_response_error(self, mock_aws_session):
        """Test polling when debugger returns an error."""
        # Create DynamoDB table
        dynamodb = mock_aws_session.resource("dynamodb")
        table = dynamodb.create_table(
            TableName="PLLDBDebugger",
            KeySchema=[{"AttributeName": "RequestId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "RequestId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Put item with error
        table.put_item(
            Item={
                "RequestId": "test-request-id",
                "StatusCode": 500,
                "ErrorMessage": "Debugger error occurred",
            }
        )

        # Poll for response
        response, error = lambda_runtime.poll_for_response(mock_aws_session, "test-request-id", timeout=1)

        assert response is None
        assert error == "Debugger error occurred"

    @mock_aws
    def test_poll_for_response_timeout(self, mock_aws_session):
        """Test polling timeout."""
        # Create DynamoDB table
        dynamodb = mock_aws_session.resource("dynamodb")
        dynamodb.create_table(
            TableName="PLLDBDebugger",
            KeySchema=[{"AttributeName": "RequestId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "RequestId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Poll for non-existent response with short timeout
        response, error = lambda_runtime.poll_for_response(mock_aws_session, "test-request-id", timeout=1)

        assert response is None
        assert error == "Timeout waiting for debugger response"

    @patch("boto3.Session.client")
    def test_send_debugger_request_success(self, mock_client, monkeypatch):
        """Test successful WebSocket notification."""
        monkeypatch.setenv(
            "DEBUGGER_WEBSOCKET_API_ENDPOINT",
            "https://test.execute-api.us-east-1.amazonaws.com/prod",
        )

        # Mock API Gateway Management API client
        mock_api_client = Mock()
        mock_client.return_value = mock_api_client

        # Create mock session
        mock_session = Mock(spec=boto3.Session)
        mock_session.client = mock_client

        # Test notification
        message = {"action": "test", "data": "value"}
        lambda_runtime.send_debugger_request(mock_session, "test-connection-id", message)

        # Verify API call
        mock_api_client.post_to_connection.assert_called_once_with(ConnectionId="test-connection-id", Data=json.dumps(message).encode())

    @patch("boto3.Session.client")
    def test_send_debugger_request_error(self, mock_client, monkeypatch):
        """Test WebSocket notification error handling (should not raise)."""
        monkeypatch.setenv(
            "DEBUGGER_WEBSOCKET_API_ENDPOINT",
            "https://test.execute-api.us-east-1.amazonaws.com/prod",
        )

        # Mock API Gateway Management API client that raises error
        mock_api_client = Mock()
        mock_api_client.post_to_connection.side_effect = Exception("Connection error")
        mock_client.return_value = mock_api_client

        # Create mock session
        mock_session = Mock(spec=boto3.Session)
        mock_session.client = mock_client

        # Test notification - should not raise
        lambda_runtime.send_debugger_request(mock_session, "test-connection-id", {"test": "data"})

        # Verify API was called despite error
        assert mock_api_client.post_to_connection.called


class TestNormalHandlerExecution:
    """Test normal Lambda handler execution."""

    @patch("urllib.request.urlopen")
    def test_run_normal_handler_success(self, mock_urlopen, monkeypatch):
        """Test successful execution of normal handler."""
        # Setup environment
        monkeypatch.setenv("_HANDLER", "test_handler.handler")
        monkeypatch.setenv("LAMBDA_TASK_ROOT", "/var/task")
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "test-function")

        # Mock urlopen for send_response
        mock_response = Mock()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        # Create a mock handler module
        mock_handler_module = Mock()
        mock_handler_module.handler = Mock(return_value={"statusCode": 200, "body": "Success"})

        # Mock __import__
        with patch("builtins.__import__", return_value=mock_handler_module):
            lambda_runtime.run_normal_handler({"test": "event"}, "test-request-id", "127.0.0.1:9001")

        # Verify handler was called
        mock_handler_module.handler.assert_called_once()
        args = mock_handler_module.handler.call_args[0]
        assert args[0] == {"test": "event"}
        assert args[1].aws_request_id == "test-request-id"

        # Verify response was sent
        assert mock_urlopen.called

    @patch("urllib.request.urlopen")
    def test_run_normal_handler_no_handler(self, mock_urlopen, monkeypatch):
        """Test error when handler is not specified."""
        # No _HANDLER environment variable
        monkeypatch.delenv("_HANDLER", raising=False)

        # Mock urlopen for send_error
        mock_response = Mock()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        lambda_runtime.run_normal_handler({}, "test-request-id", "127.0.0.1:9001")

        # Verify error was sent
        args, kwargs = mock_urlopen.call_args
        request = args[0]
        assert "/error" in request.get_full_url()


class TestMainLoop:
    """Test main function and the runtime loop."""

    class StopLoopException(Exception):
        """Custom exception to break out of the infinite loop during tests."""

        pass

    @patch("plldb.cloudformation.layer.lambda_runtime.get_next_invocation")
    @patch("plldb.cloudformation.layer.lambda_runtime.run_normal_handler")
    def test_main_normal_mode(self, mock_run_normal, mock_get_next, monkeypatch):
        """Test main in normal mode without debug environment variables."""
        monkeypatch.setenv("AWS_LAMBDA_RUNTIME_API", "127.0.0.1:9001")
        monkeypatch.delenv("DEBUGGER_SESSION_ID", raising=False)
        monkeypatch.delenv("DEBUGGER_CONNECTION_ID", raising=False)

        # First call returns event, second call raises to exit loop
        mock_get_next.side_effect = [({"test": "event"}, "request-1"), self.StopLoopException("Exit loop")]

        with pytest.raises(self.StopLoopException):
            lambda_runtime.main()

        # Verify normal handler was called
        mock_run_normal.assert_called_once_with({"test": "event"}, "request-1", "127.0.0.1:9001")

    @patch("plldb.cloudformation.layer.lambda_runtime.get_next_invocation")
    @patch("plldb.cloudformation.layer.lambda_runtime.assume_debugger_role")
    @patch("plldb.cloudformation.layer.lambda_runtime.create_debugger_request")
    @patch("plldb.cloudformation.layer.lambda_runtime.send_debugger_request")
    @patch("plldb.cloudformation.layer.lambda_runtime.poll_for_response")
    @patch("plldb.cloudformation.layer.lambda_runtime.send_response")
    def test_main_debug_mode_success(self, mock_send_response, mock_poll, mock_send_debugger_request, mock_create_request, mock_assume_role, mock_get_next, monkeypatch):
        """Test main in debug mode with successful response."""
        monkeypatch.setenv("AWS_LAMBDA_RUNTIME_API", "127.0.0.1:9001")
        monkeypatch.setenv("DEBUGGER_SESSION_ID", "test-session")
        monkeypatch.setenv("DEBUGGER_CONNECTION_ID", "test-connection")
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "test-function")

        # Setup mocks
        mock_session = Mock()
        mock_assume_role.return_value = mock_session
        mock_poll.return_value = ({"result": "success"}, None)

        # First call returns event, second raises to exit
        mock_get_next.side_effect = [({"test": "event"}, "request-1"), self.StopLoopException("Exit loop")]

        with pytest.raises(self.StopLoopException):
            lambda_runtime.main()

        # Verify debug flow
        mock_assume_role.assert_called_once()
        mock_create_request.assert_called_once_with(
            mock_session,
            "request-1",
            "test-session",
            "test-connection",
            {"test": "event"},
            {"aws_request_id": "request-1", "function_name": "test-function", "function_version": "", "invoked_function_arn": "", "memory_limit_in_mb": ""},
        )
        mock_send_debugger_request.assert_called_once()
        mock_poll.assert_called_once_with(mock_session, "request-1")
        mock_send_response.assert_called_once_with("127.0.0.1:9001", "request-1", {"result": "success"})

    @patch("plldb.cloudformation.layer.lambda_runtime.get_next_invocation")
    @patch("plldb.cloudformation.layer.lambda_runtime.assume_debugger_role")
    @patch("plldb.cloudformation.layer.lambda_runtime.create_debugger_request")
    @patch("plldb.cloudformation.layer.lambda_runtime.send_debugger_request")
    @patch("plldb.cloudformation.layer.lambda_runtime.poll_for_response")
    @patch("plldb.cloudformation.layer.lambda_runtime.send_error")
    def test_main_debug_mode_with_error(self, mock_send_error, mock_poll, mock_send_debugger_request, mock_create_request, mock_assume_role, mock_get_next, monkeypatch):
        """Test main in debug mode when debugger returns error."""
        monkeypatch.setenv("AWS_LAMBDA_RUNTIME_API", "127.0.0.1:9001")
        monkeypatch.setenv("DEBUGGER_SESSION_ID", "test-session")
        monkeypatch.setenv("DEBUGGER_CONNECTION_ID", "test-connection")

        # Setup mocks
        mock_session = Mock()
        mock_assume_role.return_value = mock_session
        mock_poll.return_value = (None, "Debugger error")

        # First call returns event, second raises to exit
        mock_get_next.side_effect = [({"test": "event"}, "request-1"), self.StopLoopException("Exit loop")]

        with pytest.raises(self.StopLoopException):
            lambda_runtime.main()

        # Verify error was sent
        mock_send_error.assert_called_once_with("127.0.0.1:9001", "request-1", "Debugger error")

    @patch("plldb.cloudformation.layer.lambda_runtime.get_next_invocation")
    @patch("plldb.cloudformation.layer.lambda_runtime.assume_debugger_role")
    @patch("plldb.cloudformation.layer.lambda_runtime.send_error")
    def test_main_debug_mode_role_assumption_failure(self, mock_send_error, mock_assume_role, mock_get_next, monkeypatch):
        """Test main when debugger role assumption fails."""
        monkeypatch.setenv("AWS_LAMBDA_RUNTIME_API", "127.0.0.1:9001")
        monkeypatch.setenv("DEBUGGER_SESSION_ID", "test-session")
        monkeypatch.setenv("DEBUGGER_CONNECTION_ID", "test-connection")

        # Setup mocks
        mock_assume_role.side_effect = Exception("Role assumption failed")

        # First call returns event, second raises to exit
        mock_get_next.side_effect = [({"test": "event"}, "request-1"), self.StopLoopException("Exit loop")]

        with pytest.raises(self.StopLoopException):
            lambda_runtime.main()

        # Verify error was sent
        mock_send_error.assert_called_once_with("127.0.0.1:9001", "request-1", "Debugger error: Role assumption failed")

    @patch("plldb.cloudformation.layer.lambda_runtime.get_next_invocation")
    @patch("plldb.cloudformation.layer.lambda_runtime.assume_debugger_role")
    @patch("plldb.cloudformation.layer.lambda_runtime.create_debugger_request")
    @patch("plldb.cloudformation.layer.lambda_runtime.send_error")
    def test_main_debug_mode_create_request_failure(self, mock_send_error, mock_create_request, mock_assume_role, mock_get_next, monkeypatch):
        """Test main when creating debugger request fails."""
        monkeypatch.setenv("AWS_LAMBDA_RUNTIME_API", "127.0.0.1:9001")
        monkeypatch.setenv("DEBUGGER_SESSION_ID", "test-session")
        monkeypatch.setenv("DEBUGGER_CONNECTION_ID", "test-connection")

        # Setup mocks
        mock_session = Mock()
        mock_assume_role.return_value = mock_session
        mock_create_request.side_effect = Exception("DynamoDB error")

        # First call returns event, second raises to exit
        mock_get_next.side_effect = [({"test": "event"}, "request-1"), self.StopLoopException("Exit loop")]

        with pytest.raises(self.StopLoopException):
            lambda_runtime.main()

        # Verify error was sent
        mock_send_error.assert_called_once_with("127.0.0.1:9001", "request-1", "Debugger error: DynamoDB error")

    @patch("plldb.cloudformation.layer.lambda_runtime.get_next_invocation")
    @patch("plldb.cloudformation.layer.lambda_runtime.run_normal_handler")
    def test_main_continues_on_handler_error(self, mock_run_normal, mock_get_next, monkeypatch):
        """Test main continues loop when handler raises exception."""
        monkeypatch.setenv("AWS_LAMBDA_RUNTIME_API", "127.0.0.1:9001")
        monkeypatch.delenv("DEBUGGER_SESSION_ID", raising=False)
        monkeypatch.delenv("DEBUGGER_CONNECTION_ID", raising=False)

        # Setup mocks - normal handler throws exception on first call
        mock_get_next.side_effect = [({"test": "event1"}, "request-1"), ({"test": "event2"}, "request-2"), self.StopLoopException("Exit loop")]
        mock_run_normal.side_effect = [
            Exception("Handler error"),
            None,  # Second call succeeds
        ]

        with pytest.raises(self.StopLoopException):
            lambda_runtime.main()

        # Verify both invocations were processed despite first error
        assert mock_get_next.call_count == 3
        assert mock_run_normal.call_count == 2

    @patch("plldb.cloudformation.layer.lambda_runtime.get_next_invocation")
    @patch("plldb.cloudformation.layer.lambda_runtime.assume_debugger_role")
    @patch("plldb.cloudformation.layer.lambda_runtime.create_debugger_request")
    @patch("plldb.cloudformation.layer.lambda_runtime.send_debugger_request")
    @patch("plldb.cloudformation.layer.lambda_runtime.poll_for_response")
    @patch("plldb.cloudformation.layer.lambda_runtime.send_response")
    def test_main_debug_mode_websocket_error_ignored(self, mock_send_response, mock_poll, mock_send_debugger_request, mock_create_request, mock_assume_role, mock_get_next, monkeypatch):
        """Test that WebSocket errors are handled gracefully."""
        monkeypatch.setenv("AWS_LAMBDA_RUNTIME_API", "127.0.0.1:9001")
        monkeypatch.setenv("DEBUGGER_SESSION_ID", "test-session")
        monkeypatch.setenv("DEBUGGER_CONNECTION_ID", "test-connection")

        # Setup mocks
        mock_session = Mock()
        mock_assume_role.return_value = mock_session
        mock_send_debugger_request.side_effect = Exception("WebSocket error")
        mock_poll.return_value = ({"result": "success"}, None)

        # Mock send_error to capture the error call
        mock_send_error = Mock()
        monkeypatch.setattr("plldb.cloudformation.layer.lambda_runtime.send_error", mock_send_error)

        # First call returns event, second raises to exit
        mock_get_next.side_effect = [({"test": "event"}, "request-1"), self.StopLoopException("Exit loop")]

        with pytest.raises(self.StopLoopException):
            lambda_runtime.main()

        # Verify error was sent due to WebSocket failure
        mock_send_error.assert_called_once()
        args = mock_send_error.call_args[0]
        assert args[0] == "127.0.0.1:9001"
        assert args[1] == "request-1"
        assert "Debugger error: WebSocket error" in args[2]

        # Verify poll was not called since we errored out earlier
        mock_poll.assert_not_called()
        mock_send_response.assert_not_called()
