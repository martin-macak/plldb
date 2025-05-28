import boto3
import logging
import os
import json
from typing import Dict, Any, Optional

logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # noqa: ARG001
    """Authorize WebSocket connections based on sessionId.

    This function validates that:
    1. A sessionId is provided in the query parameters
    2. The sessionId exists in the PLLDBSessions table
    3. The session status is PENDING
    """
    logger.debug(f"Event: {json.dumps(event)}")

    try:
        # Extract sessionId from query parameters
        query_params = event.get("queryStringParameters", {})
        session_id = query_params.get("sessionId") if query_params else None

        if not session_id:
            logger.warning(f"Unauthorized access: missing sessionId. The sessionId was supposed to be set by the authorizer.")
            result = generate_policy("user", "Deny", event["methodArn"])
            logger.debug(f"Return value: {json.dumps(result)}")
            return result

        assert session_id, "sessionId is required"

        # Check session in DynamoDB
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("PLLDBSessions")

        response = table.get_item(Key={"SessionId": session_id})

        if "Item" not in response:
            # Session doesn't exist
            logger.info(f"Unauthorized access: session not found {session_id=}")
            result = generate_policy("user", "Deny", event["methodArn"])
            logger.debug(f"Return value: {json.dumps(result)}")
            return result

        session = response["Item"]

        # Check if session is PENDING
        if session.get("Status") != "PENDING":
            logger.info(f"Unauthorized access: session not PENDING {session_id=} status={session.get('Status')}")
            result = generate_policy("user", "Deny", event["methodArn"])
            logger.debug(f"Return value: {json.dumps(result)}")
            return result

        # Session is valid - allow connection
        # Pass the sessionId as context so the connect handler can use it
        logger.info(f"Session authorized: {session_id=}")
        policy = generate_policy(
            "user",
            "Allow",
            event["methodArn"],
            context={"sessionId": session_id},
        )
        logger.debug(f"Return value: {json.dumps(policy)}")
        return policy

    except Exception as e:
        logger.error(f"Authorization error: {e=}")
        result = generate_policy("user", "Deny", event["methodArn"])
        logger.debug(f"Return value: {json.dumps(result)}")
        return result


def generate_policy(
    principal_id: str,
    effect: str,
    resource: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate an IAM policy for API Gateway."""
    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [{"Action": "execute-api:Invoke", "Effect": effect, "Resource": resource}],
        },
        **({"context": context} if context else {}),
    }
