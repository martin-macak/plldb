import json
import boto3
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle WebSocket connection and update session status."""
    logger.debug(f"Event: {json.dumps(event)}")

    try:
        # Get connection ID and session ID
        connection_id = event["requestContext"]["connectionId"]

        # The authorizer should pass the sessionId in the request context
        authorizer_context = event["requestContext"].get("authorizer", {})
        session_id = authorizer_context.get("sessionId")

        if not session_id:
            # This shouldn't happen if authorizer is working correctly
            logger.info(f"Unauthorized access attempted: {connection_id=}")
            result = {"statusCode": 403, "body": json.dumps({"error": "No session ID found"})}
            logger.debug(f"Return value: {json.dumps(result)}")
            return result

        # Update session status to ACTIVE and store connection ID
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("PLLDBSessions")

        table.update_item(
            Key={"SessionId": session_id},
            UpdateExpression="SET #status = :status, ConnectionId = :conn_id",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "ACTIVE", ":conn_id": connection_id},
        )

        logger.info(f"Session connected: {session_id=}")
        result = {"statusCode": 200, "body": json.dumps({"message": "Connected", "sessionId": session_id})}
        logger.debug(f"Return value: {json.dumps(result)}")
        return result

    except Exception as e:
        logger.error(f"Connection error: {e=}")
        result = {"statusCode": 500, "body": json.dumps({"error": str(e)})}
        logger.debug(f"Return value: {json.dumps(result)}")
        return result
