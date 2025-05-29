import json
import boto3
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def invoke_instrumentation_lambda(command: str, stack_name: str, session_id: str | None = None, connection_id: str | None = None) -> None:
    """Invoke the instrumentation lambda function asynchronously."""
    lambda_client = boto3.client("lambda")

    # Prepare the payload
    payload = {"command": command, "stackName": stack_name}

    if session_id:
        payload["sessionId"] = session_id
    if connection_id:
        payload["connectionId"] = connection_id

    try:
        # Invoke the instrumentation lambda asynchronously
        response = lambda_client.invoke(
            FunctionName="plldb-debugger-instrumentation",
            InvocationType="Event",  # Asynchronous invocation
            Payload=json.dumps(payload),
        )

        logger.info(f"Instrumentation lambda invoked asynchronously: {command=} {stack_name=} StatusCode={response['StatusCode']}")

    except Exception as e:
        logger.error(f"Failed to invoke instrumentation lambda: {e}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # noqa: ARG001
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
            result = {
                "statusCode": 403,
                "body": json.dumps({"error": "No session ID found"}),
            }
            logger.debug(f"Return value: {json.dumps(result)}")
            return result

        # Update session status to ACTIVE and store connection ID
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("PLLDBSessions")

        # Get session details including stack name
        response = table.get_item(Key={"SessionId": session_id})
        if "Item" not in response:
            logger.error(f"Session not found: {session_id=}")
            result = {
                "statusCode": 404,
                "body": json.dumps({"error": "Session not found"}),
            }
            logger.debug(f"Return value: {json.dumps(result)}")
            return result

        stack_name = response["Item"].get("StackName")
        if not stack_name:
            logger.error(f"No stack name found for session: {session_id=}")
            result = {
                "statusCode": 400,
                "body": json.dumps({"error": "No stack name in session"}),
            }
            logger.debug(f"Return value: {json.dumps(result)}")
            return result

        # Update session with connection ID and set status to ACTIVE
        table.update_item(
            Key={"SessionId": session_id},
            UpdateExpression="SET #status = :status, ConnectionId = :conn_id",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "ACTIVE", ":conn_id": connection_id},
        )

        # Invoke instrumentation lambda asynchronously
        invoke_instrumentation_lambda("instrument", stack_name, session_id, connection_id)

        logger.info(f"Session connected and instrumentation initiated: {session_id=} {stack_name=}")
        result = {
            "statusCode": 200,
            "body": json.dumps({"message": "Connected", "sessionId": session_id}),
        }
        logger.debug(f"Return value: {json.dumps(result)}")
        return result

    except Exception as e:
        logger.error(f"Connection error: {e=}")
        result = {"statusCode": 500, "body": json.dumps({"error": str(e)})}
        logger.debug(f"Return value: {json.dumps(result)}")
        return result
