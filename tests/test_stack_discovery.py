from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from plldb.stack_discovery import StackDiscovery


class TestStackDiscovery:
    @patch("boto3.Session")
    def test_get_stack_outputs_success(self, mock_session_class):
        """Test successful retrieval of stack outputs."""
        # Mock CloudFormation client
        mock_cfn_client = Mock()
        mock_cfn_client.describe_stacks.return_value = {
            "Stacks": [
                {
                    "StackName": "test-stack",
                    "Outputs": [
                        {"OutputKey": "WebSocketURL", "OutputValue": "wss://test.execute-api.us-east-1.amazonaws.com/prod"},
                        {"OutputKey": "ManagementAPIURL", "OutputValue": "https://test.execute-api.us-east-1.amazonaws.com/prod"},
                    ],
                }
            ]
        }

        # Mock session
        mock_session = Mock()
        mock_session.client.return_value = mock_cfn_client
        mock_session_class.return_value = mock_session

        discovery = StackDiscovery(mock_session)
        outputs = discovery.get_stack_outputs("test-stack")

        assert outputs == {
            "WebSocketURL": "wss://test.execute-api.us-east-1.amazonaws.com/prod",
            "ManagementAPIURL": "https://test.execute-api.us-east-1.amazonaws.com/prod",
        }
        mock_cfn_client.describe_stacks.assert_called_once_with(StackName="test-stack")

    @patch("boto3.Session")
    def test_get_stack_outputs_not_found(self, mock_session_class):
        """Test error when stack not found."""
        # Mock CloudFormation client with error
        mock_cfn_client = Mock()
        mock_cfn_client.describe_stacks.side_effect = ClientError({"Error": {"Code": "ValidationError", "Message": "Stack not found"}}, "describe_stacks")

        # Mock session
        mock_session = Mock()
        mock_session.client.return_value = mock_cfn_client
        mock_session_class.return_value = mock_session

        discovery = StackDiscovery(mock_session)
        with pytest.raises(ValueError, match="Stack 'test-stack' not found"):
            discovery.get_stack_outputs("test-stack")

    @patch("boto3.Session")
    def test_get_stack_outputs_no_outputs(self, mock_session_class):
        """Test error when stack has no outputs."""
        # Mock CloudFormation client
        mock_cfn_client = Mock()
        mock_cfn_client.describe_stacks.return_value = {"Stacks": [{"StackName": "test-stack", "Outputs": []}]}

        # Mock session
        mock_session = Mock()
        mock_session.client.return_value = mock_cfn_client
        mock_session_class.return_value = mock_session

        discovery = StackDiscovery(mock_session)
        with pytest.raises(ValueError, match="Stack 'test-stack' has no outputs"):
            discovery.get_stack_outputs("test-stack")

    @patch("boto3.Session")
    def test_get_api_endpoints_success(self, mock_session_class):
        """Test successful retrieval of API endpoints."""
        # Mock CloudFormation client
        mock_cfn_client = Mock()
        mock_cfn_client.describe_stacks.return_value = {
            "Stacks": [
                {
                    "StackName": "test-stack",
                    "Outputs": [
                        {"OutputKey": "WebSocketURL", "OutputValue": "wss://test.execute-api.us-east-1.amazonaws.com/prod"},
                        {"OutputKey": "ManagementAPIURL", "OutputValue": "https://test.execute-api.us-east-1.amazonaws.com/prod"},
                    ],
                }
            ]
        }

        # Mock session
        mock_session = Mock()
        mock_session.client.return_value = mock_cfn_client
        mock_session_class.return_value = mock_session

        discovery = StackDiscovery(mock_session)
        endpoints = discovery.get_api_endpoints("test-stack")

        assert endpoints == {
            "websocket_url": "wss://test.execute-api.us-east-1.amazonaws.com/prod",
            "rest_api_url": "https://test.execute-api.us-east-1.amazonaws.com/prod",
        }

    @patch("boto3.Session")
    def test_get_api_endpoints_missing_websocket(self, mock_session_class):
        """Test error when WebSocket URL is missing."""
        # Mock CloudFormation client
        mock_cfn_client = Mock()
        mock_cfn_client.describe_stacks.return_value = {
            "Stacks": [{"StackName": "test-stack", "Outputs": [{"OutputKey": "ManagementAPIURL", "OutputValue": "https://test.execute-api.us-east-1.amazonaws.com/prod"}]}]
        }

        # Mock session
        mock_session = Mock()
        mock_session.client.return_value = mock_cfn_client
        mock_session_class.return_value = mock_session

        discovery = StackDiscovery(mock_session)
        with pytest.raises(ValueError, match="WebSocketURL output not found in stack"):
            discovery.get_api_endpoints("test-stack")

    @patch("boto3.Session")
    def test_get_api_endpoints_missing_rest_api(self, mock_session_class):
        """Test error when REST API URL is missing."""
        # Mock CloudFormation client
        mock_cfn_client = Mock()
        mock_cfn_client.describe_stacks.return_value = {
            "Stacks": [{"StackName": "test-stack", "Outputs": [{"OutputKey": "WebSocketURL", "OutputValue": "wss://test.execute-api.us-east-1.amazonaws.com/prod"}]}]
        }

        # Mock session
        mock_session = Mock()
        mock_session.client.return_value = mock_cfn_client
        mock_session_class.return_value = mock_session

        discovery = StackDiscovery(mock_session)
        with pytest.raises(ValueError, match="ManagementAPIURL output not found in stack"):
            discovery.get_api_endpoints("test-stack")
