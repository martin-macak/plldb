import logging
from typing import Dict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class StackDiscovery:
    """Discover stack resources and endpoints from CloudFormation."""

    def __init__(self, session: boto3.Session):
        self.session = session
        self.cfn_client = session.client("cloudformation")

    def get_stack_outputs(self, stack_name: str) -> Dict[str, str]:
        """Get outputs from a CloudFormation stack.

        Args:
            stack_name: Name of the CloudFormation stack

        Returns:
            Dictionary of output key-value pairs

        Raises:
            ValueError: If stack not found or has no outputs
        """
        try:
            response = self.cfn_client.describe_stacks(StackName=stack_name)
            stacks = response.get("Stacks", [])

            if not stacks:
                raise ValueError(f"Stack '{stack_name}' not found")

            stack = stacks[0]
            outputs = stack.get("Outputs", [])

            if not outputs:
                raise ValueError(f"Stack '{stack_name}' has no outputs")

            return {output["OutputKey"]: output["OutputValue"] for output in outputs}

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ValidationError":
                raise ValueError(f"Stack '{stack_name}' not found") from e
            raise

    def get_api_endpoints(self, stack_name: str) -> Dict[str, str]:
        """Get API endpoints from stack outputs.

        Args:
            stack_name: Name of the CloudFormation stack

        Returns:
            Dictionary with 'websocket_url' and 'rest_api_url' keys

        Raises:
            ValueError: If required outputs not found
        """
        outputs = self.get_stack_outputs(stack_name)

        websocket_url = outputs.get("WebSocketURL")
        rest_api_url = outputs.get("ManagementAPIURL")

        if not websocket_url:
            raise ValueError("WebSocketURL output not found in stack")

        if not rest_api_url:
            raise ValueError("ManagementAPIURL output not found in stack")

        return {"websocket_url": websocket_url, "rest_api_url": rest_api_url}
