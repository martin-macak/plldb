# REQ-FN-0005: Attach debugger to the stack

Adds a new command `plldb attach --stack-name <stack-name>` to the CLI.
This command generates a debug session token that can be used to attach the debugger to the stack. It then opens a connection to the WebSocket API and waits for the debugger messages.

This is a follow up to [REQ-FN-0004](./req_fn_0004.md).

## Acceptance Criteria

- new command `plldb attach --stack-name <stack-name>` is added to the CLI
- the command tool is able to discover the API endpoints from the deployed stack
- the command tool creates a new session using the REST API under current AWS IAM credentials. 
- the command tool then opens a connection to the WebSocket API and waits for the debugger messages.
- the command tool enters the loop and waits for the debugger messages.
- the loop is terminated by CTRL+C or SIGINT

## Implementation notes

- use botocore to make SIGv4 signed requests to the REST API
- always use SIGv4 requests when communicating with the REST API
- use the sessionId from the REST API response to open a connection to the WebSocket API
- pass the sessionId as a query param to the WebSocket API as sessionId
