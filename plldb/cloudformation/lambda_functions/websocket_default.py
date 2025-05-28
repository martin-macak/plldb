import json
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # noqa: ARG001
    """Default route handler for WebSocket API."""
    logger.debug(f"Event: {json.dumps(event)}")

    result = {"statusCode": 200, "body": "Default route"}
    logger.debug(f"Return value: {json.dumps(result)}")
    return result
