# REQ-FN-0008: Debugger Instrumentation

When the connection is established, the debugged stack lambda functions must be instrumented.

## Acceptance Criteria

- after the connection is established, the debugged stack lambda functions must be instrumented
- every lambda function in the instrumented stack must have the `DEBUGGER_SESSION_ID` and `DEBUGGER_CONNECTION_ID` environment variables set
- every lambda function in the instrumented stack must have the `AWS_LAMBDA_EXEC_WRAPPER` environment variable set to `/opt/bin/bootstrap`
- every lambda function in the instrumented stack must have the the PLLDBDebuggerRuntime layer attached
- after the connection is broken, the instrumented stack lambda functions must be de-instrumented

## Implementation Notes

- connection is established in WebSocket
- connection handler is `plldb/cloudformation/lambda_functions/websocket_connect.py`
- disconnect handler is `plldb/cloudformation/lambda_functions/websocket_disconnect.py`
- put all the logic into the lambda handler modules. 
- do not create any additional lambda functions.
- do not create packages or modules.
- do not assume any role in the lambda functions, use the role that's assumed by the lambda functions.
- add additional permissions to the PLLDBServiceRole role to modify lambda functions and explore the stack resources.