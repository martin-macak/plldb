import json
import boto3
import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def send_debugger_info(connection_id: str, session_id: str, log_level: str, message: str) -> None:
    """Send a DebuggerInfo message to the WebSocket connection."""
    try:
        # Get WebSocket endpoint from environment
        websocket_endpoint = os.environ.get("WEBSOCKET_ENDPOINT")
        if not websocket_endpoint:
            logger.warning("WEBSOCKET_ENDPOINT not set, cannot send debugger info")
            return

        # Create API Gateway Management API client
        client = boto3.client("apigatewaymanagementapi", endpoint_url=websocket_endpoint)

        # Create DebuggerInfo message
        info_message = {"sessionId": session_id, "connectionId": connection_id, "logLevel": log_level, "message": message, "timestamp": datetime.now(timezone.utc).isoformat()}

        # Send message to connection
        client.post_to_connection(ConnectionId=connection_id, Data=json.dumps(info_message).encode("utf-8"))

    except Exception as e:
        logger.error(f"Failed to send debugger info: {e}")


def get_latest_layer_version(lambda_client: Any, layer_name: str = "PLLDBDebuggerRuntime") -> Optional[str]:
    """Find the latest version of the PLLDBDebuggerRuntime layer."""
    try:
        # List all versions of the layer
        versions = lambda_client.list_layer_versions(LayerName=layer_name)

        if not versions.get("LayerVersions"):
            logger.error(f"No versions found for layer: {layer_name}")
            return None

        # Get the latest version (first in the list as it's ordered by version descending)
        latest_version = versions["LayerVersions"][0]
        return latest_version["LayerVersionArn"]

    except Exception as e:
        if "ResourceNotFoundException" in str(type(e)):
            logger.error(f"Layer not found: {layer_name}")
        else:
            logger.error(f"Error finding layer version: {e}")
        return None


def instrument_lambda_functions(stack_name: str, session_id: str, connection_id: str) -> None:
    """Instrument all Lambda functions in the stack with debug configuration."""
    cloudformation = boto3.client("cloudformation")
    lambda_client = boto3.client("lambda")
    iam_client = boto3.client("iam")

    # Send info message that instrumentation has begun
    send_debugger_info(connection_id, session_id, "INFO", f"Starting instrumentation for stack: {stack_name}")

    # Find the latest available PLLDBDebuggerRuntime layer version
    layer_arn = get_latest_layer_version(lambda_client)

    if not layer_arn:
        error_msg = "PLLDBDebuggerRuntime layer not found or no versions available"
        logger.error(error_msg)
        send_debugger_info(connection_id, session_id, "ERROR", f"Instrumentation failed: {error_msg}")
        return

    logger.info(f"Using layer ARN: {layer_arn}")
    send_debugger_info(connection_id, session_id, "INFO", f"Using debugger layer: {layer_arn}")

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

                # Check if already instrumented (idempotency)
                if env_vars.get("DEBUGGER_SESSION_ID") == session_id and env_vars.get("DEBUGGER_CONNECTION_ID") == connection_id:
                    logger.info(f"Function already instrumented with same session/connection: {function_name}")
                    continue

                env_vars["DEBUGGER_SESSION_ID"] = session_id
                env_vars["DEBUGGER_CONNECTION_ID"] = connection_id
                env_vars["AWS_LAMBDA_EXEC_WRAPPER"] = "/opt/bin/bootstrap"
                # Add WebSocket endpoint for the lambda runtime to use
                websocket_endpoint = os.environ.get("WEBSOCKET_ENDPOINT")
                if websocket_endpoint:
                    env_vars["DEBUGGER_WEBSOCKET_API_ENDPOINT"] = websocket_endpoint

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

                # Get the function's execution role
                function_role_arn = current_config.get("Role")
                if function_role_arn:
                    role_name = function_role_arn.split("/")[-1]

                    # Create inline policy to allow assuming PLLDBDebuggerRole
                    account_id = boto3.client("sts").get_caller_identity()["Account"]
                    policy_document = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole", "Resource": f"arn:aws:iam::{account_id}:role/PLLDBDebuggerRole"}]}

                    try:
                        iam_client.put_role_policy(RoleName=role_name, PolicyName="PLLDBAssumeRolePolicy", PolicyDocument=json.dumps(policy_document))
                        logger.info(f"Added assume role policy to {role_name}")
                    except Exception as e:
                        logger.warning(f"Failed to add assume role policy to {role_name}: {e}")
                        send_debugger_info(connection_id, session_id, "WARNING", f"Could not add assume role policy to {role_name}: {e}")

                logger.info(f"Successfully instrumented: {function_name}")
                send_debugger_info(connection_id, session_id, "INFO", f"Instrumented Lambda function: {function_name}")

            except Exception as e:
                error_msg = f"Failed to instrument function {function.get('LogicalResourceId')}: {e}"
                logger.error(error_msg)
                send_debugger_info(connection_id, session_id, "ERROR", error_msg)

    except Exception as e:
        error_msg = f"Failed to list stack resources for {stack_name}: {e}"
        logger.error(error_msg)
        send_debugger_info(connection_id, session_id, "ERROR", f"Instrumentation failed: {error_msg}")
        return

    # Send completion message
    send_debugger_info(connection_id, session_id, "INFO", f"Completed instrumentation for stack: {stack_name}")


def uninstrument_lambda_functions(stack_name: str, session_id: Optional[str] = None, connection_id: Optional[str] = None) -> None:
    """Remove debug instrumentation from all Lambda functions in the stack."""
    cloudformation = boto3.client("cloudformation")
    lambda_client = boto3.client("lambda")
    iam_client = boto3.client("iam")

    # Send info message that de-instrumentation has begun (if connection details provided)
    if connection_id and session_id:
        send_debugger_info(connection_id, session_id, "INFO", f"Starting de-instrumentation for stack: {stack_name}")

    # Note: We don't need to find the specific layer version for uninstrumentation
    # We'll remove any PLLDBDebuggerRuntime layer regardless of version

    # List all resources in the target stack
    try:
        resources = cloudformation.list_stack_resources(StackName=stack_name)

        # Find all Lambda functions in the stack
        lambda_functions = [r for r in resources["StackResourceSummaries"] if r["ResourceType"] == "AWS::Lambda::Function"]

        for function in lambda_functions:
            try:
                function_name = function["PhysicalResourceId"]
                logger.info(f"Uninstrumenting Lambda function: {function_name}")

                # Get current function configuration
                current_config = lambda_client.get_function_configuration(FunctionName=function_name)

                # Check if already uninstrumented (idempotency)
                env_vars = current_config.get("Environment", {}).get("Variables", {})
                if "DEBUGGER_SESSION_ID" not in env_vars and "DEBUGGER_CONNECTION_ID" not in env_vars:
                    logger.info(f"Function already uninstrumented: {function_name}")
                    continue

                # Remove debug environment variables
                env_vars.pop("DEBUGGER_SESSION_ID", None)
                env_vars.pop("DEBUGGER_CONNECTION_ID", None)
                env_vars.pop("AWS_LAMBDA_EXEC_WRAPPER", None)
                env_vars.pop("DEBUGGER_WEBSOCKET_API_ENDPOINT", None)

                # Remove any PLLDBDebuggerRuntime layer (regardless of version)
                layers = current_config.get("Layers", [])
                layer_arns = [layer["Arn"] for layer in layers if "PLLDBDebuggerRuntime" not in layer["Arn"]]

                # Update function configuration
                update_params = {"FunctionName": function_name, "Environment": {"Variables": env_vars} if env_vars else {}}

                # Only include Layers parameter if there are layers remaining
                if layer_arns:
                    update_params["Layers"] = layer_arns
                else:
                    # If no layers remain, we need to pass an empty list
                    update_params["Layers"] = []

                lambda_client.update_function_configuration(**update_params)

                # Remove the inline policy that allows assuming PLLDBDebuggerRole
                function_role_arn = current_config.get("Role")
                if function_role_arn:
                    role_name = function_role_arn.split("/")[-1]

                    try:
                        iam_client.delete_role_policy(RoleName=role_name, PolicyName="PLLDBAssumeRolePolicy")
                        logger.info(f"Removed assume role policy from {role_name}")
                    except iam_client.exceptions.NoSuchEntityException:
                        logger.debug(f"Policy PLLDBAssumeRolePolicy not found on role {role_name}")
                    except Exception as e:
                        logger.warning(f"Failed to remove assume role policy from {role_name}: {e}")
                        if connection_id and session_id:
                            send_debugger_info(connection_id, session_id, "WARNING", f"Could not remove assume role policy from {role_name}: {e}")

                logger.info(f"Successfully uninstrumented: {function_name}")
                if connection_id and session_id:
                    send_debugger_info(connection_id, session_id, "INFO", f"De-instrumented Lambda function: {function_name}")

            except Exception as e:
                error_msg = f"Failed to uninstrument function {function.get('LogicalResourceId')}: {e}"
                logger.error(error_msg)
                if connection_id and session_id:
                    send_debugger_info(connection_id, session_id, "ERROR", error_msg)

    except Exception as e:
        error_msg = f"Failed to list stack resources for {stack_name}: {e}"
        logger.error(error_msg)
        if connection_id and session_id:
            send_debugger_info(connection_id, session_id, "ERROR", f"De-instrumentation failed: {error_msg}")
        return

    # Send completion message
    if connection_id and session_id:
        send_debugger_info(connection_id, session_id, "INFO", f"Completed de-instrumentation for stack: {stack_name}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # noqa: ARG001
    """Handle instrumentation/uninstrumentation commands asynchronously."""
    logger.debug(f"Event: {json.dumps(event)}")

    try:
        # Extract parameters
        command = event.get("command")
        stack_name = event.get("stackName")
        session_id = event.get("sessionId")
        connection_id = event.get("connectionId")

        # Validate required parameters
        if not command or not stack_name:
            error_msg = "Missing required parameters: command and stackName"
            logger.error(error_msg)
            return {"statusCode": 400, "body": json.dumps({"error": error_msg})}

        # Execute command
        if command == "instrument":
            if not session_id or not connection_id:
                error_msg = "Missing required parameters for instrument: sessionId and connectionId"
                logger.error(error_msg)
                return {"statusCode": 400, "body": json.dumps({"error": error_msg})}

            instrument_lambda_functions(stack_name, session_id, connection_id)
            logger.info(f"Instrumentation completed for stack: {stack_name}")
            return {"statusCode": 200, "body": json.dumps({"message": f"Stack {stack_name} instrumented successfully"})}

        elif command == "uninstrument":
            uninstrument_lambda_functions(stack_name, session_id, connection_id)
            logger.info(f"Uninstrumentation completed for stack: {stack_name}")
            return {"statusCode": 200, "body": json.dumps({"message": f"Stack {stack_name} uninstrumented successfully"})}

        else:
            error_msg = f"Unknown command: {command}. Supported commands: instrument, uninstrument"
            logger.error(error_msg)
            return {"statusCode": 400, "body": json.dumps({"error": error_msg})}

    except Exception as e:
        logger.error(f"Instrumentation error: {e=}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
