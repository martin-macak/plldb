import json
import uuid
import time
import boto3
from typing import Dict, Any


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Handle REST API requests for session management."""

    # Parse request
    http_method = event.get("httpMethod", "")
    path = event.get("path", "")

    if http_method == "POST" and path == "/sessions":
        return create_session(event)

    return {"statusCode": 404, "body": json.dumps({"error": "Not Found"})}


def create_session(event: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new session in the PLLDBSessions table."""

    try:
        # Parse request body
        body = json.loads(event.get("body", "{}"))
        stack_name = body.get("stackName")

        if not stack_name:
            return {"statusCode": 400, "body": json.dumps({"error": "stackName is required"})}

        # Generate session ID
        session_id = str(uuid.uuid4())

        # Calculate TTL (1 hour from now)
        ttl = int(time.time()) + 3600

        # Create session item
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("PLLDBSessions")
        table.put_item(Item={"SessionId": session_id, "StackName": stack_name, "TTL": ttl, "Status": "PENDING"})

        return {"statusCode": 201, "body": json.dumps({"sessionId": session_id})}

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
