import json
import boto3
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)


def instrument_lambda_functions(stack_name: str, session_id: str, connection_id: str) -> None:
    """Instrument all Lambda functions in the stack with debug configuration."""
    cloudformation = boto3.client("cloudformation")
    lambda_client = boto3.client("lambda")

    # Get the PLLDBDebuggerRuntime layer ARN from the current stack
    current_stack = cloudformation.describe_stacks(StackName=os.environ.get("AWS_CLOUDFORMATION_STACK_NAME", "plldb-infrastructure"))["Stacks"][0]
    layer_arn = None
    for output in current_stack.get("Outputs", []):
        if output["OutputKey"] == "DebuggerLayerArn":
            layer_arn = output["OutputValue"]
            break

    if not layer_arn:
        logger.error("PLLDBDebuggerRuntime layer ARN not found in stack outputs")
        return

    # List all resources in the target stack
    try:
        resources = cloudformation.list_stack_resources(StackName=stack_name)

        # Find all Lambda functions in the stack
        lambda_functions = [r for r in resources["StackResourceSummaries"] if r["ResourceType"] == "AWS::Lambda::Function"]

        for function in lambda_functions:
            try:
                function_name = function["PhysicalResourceId"]
                logger.info(f"Instrumenting Lambda function: {function_name}")

                # Get current function configuration
                current_config = lambda_client.get_function_configuration(FunctionName=function_name)

                # Prepare environment variables
                env_vars = current_config.get("Environment", {}).get("Variables", {})
                env_vars["DEBUGGER_SESSION_ID"] = session_id
                env_vars["DEBUGGER_CONNECTION_ID"] = connection_id
                env_vars["AWS_LAMBDA_EXEC_WRAPPER"] = "/opt/bin/bootstrap"

                # Prepare layers - add our layer if not already present
                layers = current_config.get("Layers", [])
                layer_arns = [layer["Arn"] for layer in layers]
                if layer_arn not in layer_arns:
                    layer_arns.append(layer_arn)

                # Update function configuration
                lambda_client.update_function_configuration(
                    FunctionName=function_name,
                    Environment={"Variables": env_vars},
                    Layers=layer_arns,
                )

                logger.info(f"Successfully instrumented: {function_name}")

            except Exception as e:
                logger.error(f"Failed to instrument function {function.get('LogicalResourceId')}: {e}")

    except Exception as e:
        logger.error(f"Failed to list stack resources for {stack_name}: {e}")


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

        # Instrument Lambda functions in the target stack
        instrument_lambda_functions(stack_name, session_id, connection_id)

        logger.info(f"Session connected and stack instrumented: {session_id=} {stack_name=}")
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
