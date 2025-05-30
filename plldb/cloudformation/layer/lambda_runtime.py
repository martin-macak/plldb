#!/usr/bin/env python3
"""
PLLDB Lambda Runtime Wrapper

This script intercepts Lambda invocations when DEBUGGER_SESSION_ID and
DEBUGGER_CONNECTION_ID environment variables are set, forwarding them
to a remote debugger via WebSocket.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple
import boto3


def get_lambda_runtime_api() -> str:
    """Get the Lambda Runtime API endpoint from environment."""
    return os.environ.get("AWS_LAMBDA_RUNTIME_API", "")


def get_next_invocation(runtime_api: str) -> Tuple[Dict[str, Any], str]:
    """Get the next invocation from Lambda Runtime API."""
    url = f"http://{runtime_api}/2018-06-01/runtime/invocation/next"

    try:
        with urllib.request.urlopen(url) as response:
            request_id = response.headers.get("Lambda-Runtime-Aws-Request-Id", "")
            event = json.loads(response.read().decode())
            return event, request_id
    except Exception as e:
        print(f"Error getting next invocation: {e}", file=sys.stderr)
        raise


def send_response(runtime_api: str, request_id: str, response_data: Any) -> None:
    """Send successful response to Lambda Runtime API."""
    url = f"http://{runtime_api}/2018-06-01/runtime/invocation/{request_id}/response"

    data = json.dumps(response_data).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req):
            pass
    except Exception as e:
        print(f"Error sending response: {e}", file=sys.stderr)
        raise


def send_error(runtime_api: str, request_id: str, error_message: str, error_type: str = "Error") -> None:
    """Send error response to Lambda Runtime API."""
    url = f"http://{runtime_api}/2018-06-01/runtime/invocation/{request_id}/error"

    error_data = {"errorMessage": error_message, "errorType": error_type}

    data = json.dumps(error_data).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req):
            pass
    except Exception as e:
        print(f"Error sending error response: {e}", file=sys.stderr)
        raise


def assume_debugger_role() -> boto3.Session:
    """Assume the PLLDBDebuggerRole and return a session."""
    sts = boto3.client("sts")

    try:
        response = sts.assume_role(
            RoleArn=f"arn:aws:iam::{boto3.client('sts').get_caller_identity()['Account']}:role/PLLDBDebuggerRole", RoleSessionName="plldb-lambda-runtime", ExternalId="plldb-debugger"
        )

        credentials = response["Credentials"]
        return boto3.Session(aws_access_key_id=credentials["AccessKeyId"], aws_secret_access_key=credentials["SecretAccessKey"], aws_session_token=credentials["SessionToken"])
    except Exception as e:
        print(f"Error assuming debugger role: {e}", file=sys.stderr)
        raise


def create_debugger_request(session: boto3.Session, request_id: str, session_id: str, connection_id: str, event: Dict[str, Any], context: Dict[str, Any]) -> None:
    """Create a request entry in the PLLDBDebugger table."""
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table("PLLDBDebugger")

    try:
        table.put_item(
            Item={
                "RequestId": request_id,
                "SessionId": session_id,
                "ConnectionId": connection_id,
                "Request": json.dumps({"event": event, "context": context}),
                "EnvironmentVariables": dict(os.environ),
                "StatusCode": 0,  # Indicates pending
            }
        )
    except Exception as e:
        print(f"Error creating debugger request: {e}", file=sys.stderr)
        raise


def poll_for_response(session: boto3.Session, request_id: str, timeout: int = 300) -> Tuple[Optional[Any], Optional[str]]:
    """Poll DynamoDB for debugger response."""
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table("PLLDBDebugger")

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = table.get_item(Key={"RequestId": request_id})

            if "Item" in response:
                item = response["Item"]

                # Check if response is ready
                if item.get("StatusCode") and item["StatusCode"] > 0:
                    if "ErrorMessage" in item:
                        return None, item["ErrorMessage"]
                    elif "Response" in item:
                        return json.loads(item["Response"]), None

        except Exception as e:
            print(f"Error polling for response: {e}", file=sys.stderr)

        time.sleep(1)  # Poll every second

    return None, "Timeout waiting for debugger response"


def send_debugger_request(session: boto3.Session, connection_id: str, message: Dict[str, Any]) -> None:
    """Send notification to WebSocket connection."""
    # Get WebSocket API endpoint from environment
    websocket_endpoint = os.environ.get("DEBUGGER_WEBSOCKET_API_ENDPOINT")
    if not websocket_endpoint:
        print("DEBUGGER_WEBSOCKET_API_ENDPOINT not set", file=sys.stderr)
        return

    apigateway = session.client("apigatewaymanagementapi", endpoint_url=websocket_endpoint)

    try:
        apigateway.post_to_connection(ConnectionId=connection_id, Data=json.dumps(message).encode())
    except Exception as e:
        print(f"Error sending WebSocket notification: {e}", file=sys.stderr)
        # Don't raise - WebSocket errors shouldn't fail the invocation


def run_normal_handler(event: Dict[str, Any], request_id: str, runtime_api: str) -> None:
    """Run the normal Lambda handler when not debugging."""
    # Import and execute the original handler
    handler_name = os.environ.get("_HANDLER", "")
    if not handler_name:
        send_error(runtime_api, request_id, "No handler specified")
        return

    try:
        module_name, function_name = handler_name.rsplit(".", 1)
        sys.path.insert(0, os.environ.get("LAMBDA_TASK_ROOT", "/var/task"))

        module = __import__(module_name, fromlist=[function_name])
        handler = getattr(module, function_name)

        # Create context object
        context = type(
            "LambdaContext",
            (),
            {
                "aws_request_id": request_id,
                "function_name": os.environ.get("AWS_LAMBDA_FUNCTION_NAME", ""),
                "function_version": os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", ""),
                "invoked_function_arn": os.environ.get("AWS_LAMBDA_FUNCTION_INVOKED_ARN", ""),
                "memory_limit_in_mb": os.environ.get("AWS_LAMBDA_FUNCTION_MEMORY_SIZE", ""),
                "remaining_time_in_millis": lambda: 300000,  # Placeholder
            },
        )()

        result = handler(event, context)
        send_response(runtime_api, request_id, result)

    except Exception as e:
        send_error(runtime_api, request_id, str(e), type(e).__name__)


def main():
    """Main runtime loop."""
    runtime_api = get_lambda_runtime_api()
    if not runtime_api:
        print("AWS_LAMBDA_RUNTIME_API not set", file=sys.stderr)
        sys.exit(1)

    # Check if debugging is enabled
    session_id = os.environ.get("DEBUGGER_SESSION_ID")
    connection_id = os.environ.get("DEBUGGER_CONNECTION_ID")

    while True:
        try:
            # Get next invocation
            event, request_id = get_next_invocation(runtime_api)

            if session_id and connection_id:
                # Debugging mode
                try:
                    # Assume debugger role
                    debugger_session = assume_debugger_role()

                    # Create context dict
                    context = {
                        "aws_request_id": request_id,
                        "function_name": os.environ.get("AWS_LAMBDA_FUNCTION_NAME", ""),
                        "function_version": os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", ""),
                        "invoked_function_arn": os.environ.get("AWS_LAMBDA_FUNCTION_INVOKED_ARN", ""),
                        "memory_limit_in_mb": os.environ.get("AWS_LAMBDA_FUNCTION_MEMORY_SIZE", ""),
                    }

                    # Create request in DynamoDB
                    create_debugger_request(debugger_session, request_id, session_id, connection_id, event, context)

                    # Send WebSocket notification with DebuggerRequest schema
                    websocket_message = {
                        "requestId": request_id,
                        "sessionId": session_id,
                        "connectionId": connection_id,
                        "lambdaFunctionName": os.environ.get("AWS_LAMBDA_FUNCTION_NAME", ""),
                        "lambdaFunctionVersion": os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", ""),
                        "event": json.dumps(event),
                        "environmentVariables": dict(os.environ),
                    }
                    send_debugger_request(debugger_session, connection_id, websocket_message)

                    # Poll for response
                    response, error = poll_for_response(debugger_session, request_id)

                    if error:
                        send_error(runtime_api, request_id, error)
                    else:
                        send_response(runtime_api, request_id, response)

                except Exception as e:
                    send_error(runtime_api, request_id, f"Debugger error: {str(e)}")
            else:
                # Normal mode - run the handler directly
                run_normal_handler(event, request_id, runtime_api)

        except Exception as e:
            print(f"Runtime error: {e}", file=sys.stderr)

            if e.__class__.__name__ == "StopLoopException":
                raise
            else:
                # Continue to next invocation
                pass


if __name__ == "__main__":
    main()
