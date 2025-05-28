import json
from unittest.mock import Mock, patch

import pytest

from plldb.rest_client import RestApiClient


class TestRestApiClient:
    @patch("requests.post")
    def test_create_session_success(self, mock_post):
        """Test successful session creation."""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"sessionId": "test-session-id"}
        mock_post.return_value = mock_response

        # Mock session
        mock_session = Mock()
        mock_credentials = Mock()
        mock_credentials.access_key = "test-key"
        mock_credentials.secret_key = "test-secret"
        mock_credentials.token = None
        mock_session.get_credentials.return_value = mock_credentials
        mock_session.region_name = "us-east-1"

        # Test
        client = RestApiClient(mock_session)
        session_id = client.create_session("https://api.example.com", "test-stack")

        assert session_id == "test-session-id"

        # Verify request
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.kwargs["timeout"] == 30
        assert json.loads(call_args.kwargs["data"]) == {"stackName": "test-stack"}

    @patch("requests.post")
    def test_create_session_api_error(self, mock_post):
        """Test API error handling."""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        # Mock session
        mock_session = Mock()
        mock_credentials = Mock()
        mock_credentials.access_key = "test-key"
        mock_credentials.secret_key = "test-secret"
        mock_credentials.token = None
        mock_session.get_credentials.return_value = mock_credentials
        mock_session.region_name = "us-east-1"

        # Test
        client = RestApiClient(mock_session)
        with pytest.raises(ValueError, match="Failed to create session: 400 - Bad Request"):
            client.create_session("https://api.example.com", "test-stack")

    @patch("requests.post")
    def test_create_session_no_session_id(self, mock_post):
        """Test error when no session ID returned."""
        # Mock response without sessionId
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {}
        mock_post.return_value = mock_response

        # Mock session
        mock_session = Mock()
        mock_credentials = Mock()
        mock_credentials.access_key = "test-key"
        mock_credentials.secret_key = "test-secret"
        mock_credentials.token = None
        mock_session.get_credentials.return_value = mock_credentials
        mock_session.region_name = "us-east-1"

        # Test
        client = RestApiClient(mock_session)
        with pytest.raises(ValueError, match="No sessionId returned from API"):
            client.create_session("https://api.example.com", "test-stack")
