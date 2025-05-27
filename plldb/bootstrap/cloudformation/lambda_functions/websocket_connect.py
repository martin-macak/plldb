import json
import boto3
from typing import Dict, Any


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle WebSocket connection and update session status."""

    try:
        # Get connection ID and session ID
        connection_id = event["requestContext"]["connectionId"]

        # The authorizer should pass the sessionId in the request context
        authorizer_context = event["requestContext"].get("authorizer", {})
        session_id = authorizer_context.get("sessionId")

        if not session_id:
            # This shouldn't happen if authorizer is working correctly
            return {"statusCode": 403, "body": json.dumps({"error": "No session ID found"})}

        # Update session status to ACTIVE and store connection ID
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("PLLDBSessions")

        table.update_item(
            Key={"SessionId": session_id},
            UpdateExpression="SET #status = :status, ConnectionId = :conn_id",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "ACTIVE", ":conn_id": connection_id},
        )

        return {"statusCode": 200, "body": json.dumps({"message": "Connected", "sessionId": session_id})}

    except Exception as e:
        print(f"Connection error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
