import json
import boto3
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)


def deinstrument_lambda_functions(stack_name: str) -> None:
    """Remove debug instrumentation from all Lambda functions in the stack."""
    cloudformation = boto3.client("cloudformation")
    lambda_client = boto3.client("lambda")

    # Get the PLLDBDebuggerRuntime layer ARN from the current stack
    current_stack = cloudformation.describe_stacks(StackName=os.environ.get("AWS_CLOUDFORMATION_STACK_NAME", "plldb-infrastructure"))["Stacks"][0]
    layer_arn = None
    for output in current_stack.get("Outputs", []):
        if output["OutputKey"] == "DebuggerLayerArn":
            layer_arn = output["OutputValue"]
            break

    # List all resources in the target stack
    try:
        resources = cloudformation.list_stack_resources(StackName=stack_name)

        # Find all Lambda functions in the stack
        lambda_functions = [r for r in resources["StackResourceSummaries"] if r["ResourceType"] == "AWS::Lambda::Function"]

        for function in lambda_functions:
            try:
                function_name = function["PhysicalResourceId"]
                logger.info(f"De-instrumenting Lambda function: {function_name}")

                # Get current function configuration
                current_config = lambda_client.get_function_configuration(FunctionName=function_name)

                # Remove debug environment variables
                env_vars = current_config.get("Environment", {}).get("Variables", {})
                env_vars.pop("_DEBUGGER_SESSION_ID_", None)
                env_vars.pop("_DEBUGGER_CONNECTION_ID_", None)
                env_vars.pop("_AWS_LAMBDA_EXEC_WRAPPER", None)

                # Remove our layer if present
                layers = current_config.get("Layers", [])
                layer_arns = [layer["Arn"] for layer in layers if layer["Arn"] != layer_arn]

                # Update function configuration
                update_params = {"FunctionName": function_name, "Environment": {"Variables": env_vars} if env_vars else {}}

                # Only include Layers parameter if there are layers remaining
                if layer_arns:
                    update_params["Layers"] = layer_arns
                else:
                    # If no layers remain, we need to pass an empty list
                    update_params["Layers"] = []

                lambda_client.update_function_configuration(**update_params)

                logger.info(f"Successfully de-instrumented: {function_name}")

            except Exception as e:
                logger.error(f"Failed to de-instrument function {function.get('LogicalResourceId')}: {e}")

    except Exception as e:
        logger.error(f"Failed to list stack resources for {stack_name}: {e}")


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
            stack_name = session.get("StackName")

            table.update_item(
                Key={"SessionId": session_id}, UpdateExpression="SET #status = :status", ExpressionAttributeNames={"#status": "Status"}, ExpressionAttributeValues={":status": "DISCONNECTED"}
            )
            logger.info(f"Session disconnected: {session_id=}")

            # De-instrument Lambda functions in the target stack
            if stack_name:
                deinstrument_lambda_functions(stack_name)
                logger.info(f"Stack de-instrumented: {stack_name=}")

        result = {"statusCode": 200, "body": json.dumps({"message": "Disconnected"})}
        logger.debug(f"Return value: {json.dumps(result)}")
        return result

    except Exception as e:
        logger.error(f"Disconnection error: {e=}")
        result = {"statusCode": 500, "body": json.dumps({"error": str(e)})}
        logger.debug(f"Return value: {json.dumps(result)}")
        return result
