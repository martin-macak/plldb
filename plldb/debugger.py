import json
import logging
from typing import Dict, Union
import boto3
from plldb.protocol import DebuggerRequest, DebuggerResponse, DebuggerInfo
from plldb.executor import Executor

logger = logging.getLogger(__name__)


class Debugger:
    def __init__(
        self,
        session: boto3.Session,
        stack_name: str,
    ):
        self.session = session
        self.stack_name = stack_name
        self._lambda_functions_lookup = {}
        self._executor = Executor()
        self._inspect_stack()

    def _inspect_stack(self) -> None:
        """
        Inspect the CloudFormation stack and build lookup table.
        Use list_stack_resources to list stack resources.
        Build associative map from PhysicalResourceId -> LogicalResourceId
        for resource type AWS::Lambda::Function.
        """
        # Create CloudFormation client
        logger.debug(f"Inspecting stack {self.stack_name}")

        cfn_client = self.session.client("cloudformation")

        # Get all stack resources using list_stack_resources which supports pagination
        paginator = cfn_client.get_paginator("list_stack_resources")
        page_iterator = paginator.paginate(StackName=self.stack_name)

        # Build lookup table of PhysicalResourceId -> LogicalResourceId for Lambda functions
        for page in page_iterator:
            for resource in page["StackResourceSummaries"]:
                if resource["ResourceType"] == "AWS::Lambda::Function":
                    physical_id = resource.get("PhysicalResourceId")
                    logical_id = resource.get("LogicalResourceId")
                    if physical_id and logical_id:
                        self._lambda_functions_lookup[physical_id] = logical_id
                        logger.debug(f"Found lambda function {logical_id} with physical id {physical_id}")
        logger.debug("Stack inspection complete")

    def handle_message(self, message: Dict) -> Union[DebuggerResponse, None]:
        # Check if this is a DebuggerInfo message
        if "logLevel" in message and "timestamp" in message:
            info = DebuggerInfo(**message)
            logger.debug(f"Received remote debugger message: {info.message}")
            return None

        # Otherwise, it's a DebuggerRequest
        request = DebuggerRequest(**message)
        logger.info(f"DEBUG requestId={request.requestId} for lambdaFunctionName={request.lambdaFunctionName}")
        logger.debug(f"Request: {request}")

        # The lambdaFunctionName is the physical resource ID
        lambda_function_physical_id = request.lambdaFunctionName
        lambda_function_logical_id = self._lambda_functions_lookup.get(lambda_function_physical_id)
        if not lambda_function_logical_id:
            logger.error(f"Resource {lambda_function_logical_id} not found in current stack")
            raise InvalidMessageError(f"Lambda function {lambda_function_physical_id} not found in the stack")

        try:
            response = self._executor.invoke_lambda_function(
                lambda_function_logical_id=lambda_function_logical_id,
                event=json.loads(request.event),
                environment=request.environmentVariables,
            )
            return DebuggerResponse(
                requestId=request.requestId,
                statusCode=200,
                response=json.dumps(response) if response and not isinstance(response, str) else (response or ""),
                errorMessage=None,
            )
        except Exception as e:
            return DebuggerResponse(
                requestId=request.requestId,
                statusCode=500,
                response="",
                errorMessage=str(e),
            )


class InvalidMessageError(Exception):
    pass
