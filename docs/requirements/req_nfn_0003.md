# REQ-NFN-0003: Logging messages - instrumentation

Add support for arbitrary logging messages between the backend lambdas and the debugger in command line tool.

Check the `schema/ws_debugger_info.yaml` file for the message format.
This message is sent from the backend lambda to the WebSocket connection.

When the `plldb.debugger` processes the message, it should print the message to the console.

## Acceptance criteria

- The new message type is added to `plldb.protocol`
- The `plldb.debugger` class accepts a new message type 
- The `debugger_instrumentation` lambda function sends the new message type to the WebSocket connection
  - When the instrumentation begins, info message is sent
  - When the lambda function is instrumented, info message is sent with the function name
  - When the instrumentation ends, info message is sent
  - When the instrumentation fails, error message is sent
  - When the de-instrumentation begins, info message is sent
  - When the lambda function is de-instrumented, info message is sent with the function name
  - When the de-instrumentation ends, info message is sent
  - When the de-instrumentation fails, error message is sent