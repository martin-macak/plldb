import json
import uuid
import time
import boto3
import logging
import os
from typing import Dict, Any

logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Handle REST API requests for session management."""
    logger.debug(f"Event: {json.dumps(event)}")

    # Parse request
    http_method = event.get("httpMethod", "")
    path = event.get("path", "")

    if http_method == "POST" and path == "/sessions":
        result = create_session(event)
        logger.debug(f"Return value: {json.dumps(result)}")
        return result

    logger.info(f"Unauthorized access attempted: {http_method=} {path=}")
    result = {"statusCode": 404, "body": json.dumps({"error": "Not Found"})}
    logger.debug(f"Return value: {json.dumps(result)}")
    return result


def create_session(event: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new session in the PLLDBSessions table."""

    try:
        # Parse request body
        body = json.loads(event.get("body", "{}"))
        stack_name = body.get("stackName")
        logger.debug(f"Request body: {json.dumps(body)}")

        if not stack_name:
            logger.info(f"Session creation failed: missing stackName")
            return {"statusCode": 400, "body": json.dumps({"error": "stackName is required"})}

        # Generate session ID
        session_id = str(uuid.uuid4())
        logger.info(f"Session creation: {session_id=} {stack_name=}")

        # Calculate TTL (1 hour from now)
        ttl = int(time.time()) + 3600

        # Create session item
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("PLLDBSessions")
        table.put_item(Item={"SessionId": session_id, "StackName": stack_name, "TTL": ttl, "Status": "PENDING"})

        logger.info(f"Session created successfully: {session_id=}")
        return {"statusCode": 201, "body": json.dumps({"sessionId": session_id})}

    except Exception as e:
        logger.error(f"Error creating session: {e=}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
