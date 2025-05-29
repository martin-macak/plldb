import json
from typing import Dict, Union
from plldb.protocol import DebuggerRequest, DebuggerResponse, DebuggerInfo
from plldb.executor import Executor


class Debugger:
    def __init__(
        self,
        stack_name: str,
    ):
        self.stack_name = stack_name
        self._inspect_stack()
        self._lambda_functions_lookup = {}
        self._executor = Executor()

    def _inspect_stack(self) -> None:
        """
        Inspect the CloudFormation stack and download the processed template.
        Load the processed template.
        Create lookup table of lambda functions name -> logical id
        Store the lookup table in the class
        """
        pass

    def handle_message(self, message: Dict) -> Union[DebuggerResponse, None]:
        # Check if this is a DebuggerInfo message
        if "logLevel" in message and "timestamp" in message:
            info = DebuggerInfo(**message)
            # Print the log message to console
            print(f"[{info.timestamp}] [{info.logLevel}] {info.message}")
            return None

        # Otherwise, it's a DebuggerRequest
        request = DebuggerRequest(**message)

        lambda_function_name = request.lambdaFunctionName
        lambda_function_logical_id = self._lambda_functions_lookup.get(lambda_function_name)
        if not lambda_function_logical_id:
            raise InvalidMessageError(f"Lambda function {lambda_function_name} not found in the stack")

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
