import boto3
from typing import Dict, Any, Optional


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # noqa: ARG001
    """Authorize WebSocket connections based on sessionId.

    This function validates that:
    1. A sessionId is provided in the query parameters
    2. The sessionId exists in the PLLDBSessions table
    3. The session status is PENDING
    """

    try:
        # Extract sessionId from query parameters
        query_params = event.get("queryStringParameters", {})
        session_id = query_params.get("sessionId") if query_params else None

        if not session_id:
            return generate_policy("user", "Deny", event["methodArn"])

        assert session_id, "sessionId is required"

        # Check session in DynamoDB
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("PLLDBSessions")

        response = table.get_item(Key={"SessionId": session_id})

        if "Item" not in response:
            # Session doesn't exist
            return generate_policy("user", "Deny", event["methodArn"])

        session = response["Item"]

        # Check if session is PENDING
        if session.get("Status") != "PENDING":
            return generate_policy("user", "Deny", event["methodArn"])

        # Session is valid - allow connection
        # Pass the sessionId as context so the connect handler can use it
        policy = generate_policy(
            "user",
            "Allow",
            event["methodArn"],
            context={"sessionId": session_id},
        )
        return policy

    except Exception as e:
        print(f"Authorization error: {str(e)}")
        return generate_policy("user", "Deny", event["methodArn"])


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
