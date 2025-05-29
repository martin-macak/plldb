# REQ-NFN-0002: Asynchronous instrumentation

Problem:
The instrumentation is performced in the WebSocket connection handler.
This causes the connection handler to be blocked for a long time, which is not good because the WebSocket connection times-out.

Solution:
Delegate the instrumentation to a separate lambda function.
Invoke that function asynchronously.

## Acceptance criteria

- New lambda function `debugger_instrumentation` is created
- The lambda function is invoked asynchronously from the WebSocket connection handler
- The lambda function supports two commands:
  - `instrument`
  - `uninstrument`
- The lambda function is idempotent, so it does not fail on instrumented stack for `instrument` command
- The lambda function is idempotent, so it does not fail on instrumented stack for `uninstrument` command
- The lambda function is invoked with the following parameters:
  - `command` - the command to execute
  - `stackName` - the stack name to instrument
  - `sessionId` - the session id associated with the connection
  - `connectionId` - the connection id that should be used for the notifications

## Out of scope

- notifications are not implemented yet