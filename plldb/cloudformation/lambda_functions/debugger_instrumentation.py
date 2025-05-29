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

                # Check if already instrumented (idempotency)
                if env_vars.get("DEBUGGER_SESSION_ID") == session_id and env_vars.get("DEBUGGER_CONNECTION_ID") == connection_id:
                    logger.info(f"Function already instrumented with same session/connection: {function_name}")
                    continue

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


def uninstrument_lambda_functions(stack_name: str) -> None:
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

                logger.info(f"Successfully uninstrumented: {function_name}")

            except Exception as e:
                logger.error(f"Failed to uninstrument function {function.get('LogicalResourceId')}: {e}")

    except Exception as e:
        logger.error(f"Failed to list stack resources for {stack_name}: {e}")


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
            uninstrument_lambda_functions(stack_name)
            logger.info(f"Uninstrumentation completed for stack: {stack_name}")
            return {"statusCode": 200, "body": json.dumps({"message": f"Stack {stack_name} uninstrumented successfully"})}

        else:
            error_msg = f"Unknown command: {command}. Supported commands: instrument, uninstrument"
            logger.error(error_msg)
            return {"statusCode": 400, "body": json.dumps({"error": error_msg})}

    except Exception as e:
        logger.error(f"Instrumentation error: {e=}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
