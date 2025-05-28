import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

logger = logging.getLogger(__name__)


class RestApiClient:
    """Client for making SigV4 signed requests to the PLLDB REST API."""

    def __init__(self, session: boto3.Session):
        self.session = session
        self.credentials = session.get_credentials()
        self.region = session.region_name

    def create_session(self, api_url: str, stack_name: str) -> str:
        """Create a new debug session using the REST API.

        Args:
            api_url: Base URL of the REST API
            stack_name: Name of the stack to debug

        Returns:
            Session ID from the API response

        Raises:
            ValueError: If API request fails
        """
        # Prepare request
        endpoint = f"{api_url}/sessions"
        method = "POST"
        headers = {"Content-Type": "application/json"}
        body = json.dumps({"stackName": stack_name})

        # Create AWS request
        request = AWSRequest(method=method, url=endpoint, data=body, headers=headers)

        # Sign request with SigV4
        if not self.credentials:
            raise ValueError("No AWS credentials available")
        SigV4Auth(self.credentials, "execute-api", self.region).add_auth(request)

        # Send request using prepared request
        prepared_request = request.prepare()

        # Use requests library to send the prepared request
        import requests

        # Convert body to bytes if needed
        body_data: Optional[bytes] = None
        if prepared_request.body:
            if isinstance(prepared_request.body, str):
                body_data = prepared_request.body.encode()
            elif isinstance(prepared_request.body, (bytes, bytearray)):
                body_data = bytes(prepared_request.body)

        response = requests.post(prepared_request.url, headers=dict(prepared_request.headers), data=body_data, timeout=30)

        if response.status_code != 201:
            raise ValueError(f"Failed to create session: {response.status_code} - {response.text}")

        # Parse response
        data = response.json()
        session_id = data.get("sessionId")

        if not session_id:
            raise ValueError("No sessionId returned from API")

        logger.info(f"Created session: {session_id}")
        return session_id
