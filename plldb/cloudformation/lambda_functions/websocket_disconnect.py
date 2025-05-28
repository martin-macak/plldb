import json
import boto3
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # noqa: ARG001
    """Handle WebSocket disconnection and clean up session."""
    logger.debug(f"Event: {json.dumps(event)}")

    try:
        # Get connection ID
        connection_id = event["requestContext"]["connectionId"]

        # Find and update session by ConnectionId
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("PLLDBSessions")

        # We need to scan to find the session by ConnectionId
        # In a production system, you might want to add a GSI on ConnectionId
        response = table.scan(FilterExpression="ConnectionId = :conn_id", ExpressionAttributeValues={":conn_id": connection_id})

        if response["Items"]:
            # Update the session status to DISCONNECTED
            session = response["Items"][0]
            session_id = session["SessionId"]
            table.update_item(
                Key={"SessionId": session_id}, UpdateExpression="SET #status = :status", ExpressionAttributeNames={"#status": "Status"}, ExpressionAttributeValues={":status": "DISCONNECTED"}
            )
            logger.info(f"Session disconnected: {session_id=}")

        result = {"statusCode": 200, "body": json.dumps({"message": "Disconnected"})}
        logger.debug(f"Return value: {json.dumps(result)}")
        return result

    except Exception as e:
        logger.error(f"Disconnection error: {e=}")
        result = {"statusCode": 500, "body": json.dumps({"error": str(e)})}
        logger.debug(f"Return value: {json.dumps(result)}")
        return result
