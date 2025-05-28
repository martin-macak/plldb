import json
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

import boto3

logger = logging.getLogger(__name__)


@dataclass
class DebuggerRequest:
    """WebSocket request from Lambda runtime to debugger."""

    requestId: str
    sessionId: str
    connectionId: str
    lambdaFunctionName: str
    lambdaFunctionVersion: str
    event: str
    environmentVariables: Optional[Dict[str, str]] = None


@dataclass
class DebuggerResponse:
    """WebSocket response from debugger to Lambda runtime."""

    requestId: str
    statusCode: int
    response: str
    errorMessage: Optional[str] = None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # noqa: ARG001
    """Default route handler for WebSocket API - handles debugger responses."""
    logger.debug(f"Event: {json.dumps(event)}")

    try:
        # Parse the incoming message
        body = json.loads(event.get("body", "{}"))

        # Check if this is a debugger response
        if all(key in body for key in ["requestId", "statusCode", "response"]):
            # Handle debugger response
            return handle_debugger_response(body)
        else:
            # Unknown message type
            return {"statusCode": 400, "body": json.dumps({"error": "Invalid message format"})}

    except json.JSONDecodeError:
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON in request body"})}
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": "Internal server error"})}


def handle_debugger_response(body: Dict[str, Any]) -> Dict[str, Any]:
    """Handle debugger response by updating DynamoDB."""
    try:
        # Create DebuggerResponse from body
        response = DebuggerResponse(requestId=body["requestId"], statusCode=body["statusCode"], response=body["response"], errorMessage=body.get("errorMessage"))

        # Update DynamoDB
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("PLLDBDebugger")

        # Update the item with response data
        update_expression = "SET #resp = :resp, StatusCode = :status"
        expression_attribute_names = {"#resp": "Response"}
        expression_attribute_values = {":resp": response.response, ":status": response.statusCode}

        # Add error message if present
        if response.errorMessage:
            update_expression += ", ErrorMessage = :error"
            expression_attribute_values[":error"] = response.errorMessage

        table.update_item(
            Key={"RequestId": response.requestId}, UpdateExpression=update_expression, ExpressionAttributeNames=expression_attribute_names, ExpressionAttributeValues=expression_attribute_values
        )

        logger.info(f"Updated DynamoDB for request {response.requestId}")

        return {"statusCode": 200, "body": json.dumps({"message": "Response stored successfully"})}

    except Exception as e:
        logger.error(f"Error updating DynamoDB: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to store response: {str(e)}"})}
