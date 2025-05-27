import json
import boto3
from typing import Dict, Any


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # noqa: ARG001
    """Handle WebSocket disconnection and clean up session."""
    
    try:
        # Get connection ID
        connection_id = event["requestContext"]["connectionId"]
        
        # Find and update session by ConnectionId
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("PLLDBSessions")
        
        # We need to scan to find the session by ConnectionId
        # In a production system, you might want to add a GSI on ConnectionId
        response = table.scan(
            FilterExpression="ConnectionId = :conn_id",
            ExpressionAttributeValues={
                ":conn_id": connection_id
            }
        )
        
        if response["Items"]:
            # Update the session status to DISCONNECTED
            session = response["Items"][0]
            table.update_item(
                Key={"SessionId": session["SessionId"]},
                UpdateExpression="SET #status = :status",
                ExpressionAttributeNames={"#status": "Status"},
                ExpressionAttributeValues={
                    ":status": "DISCONNECTED"
                }
            )
        
        return {"statusCode": 200, "body": json.dumps({"message": "Disconnected"})}
        
    except Exception as e:
        print(f"Disconnection error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
