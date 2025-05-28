# REQ-FN-0009 : Debugger protocol

Implement e2e debugger protocol.
Protocol schema is defined in `/schema/` dir as openapi schema.
Check [ws_debugger_request.openapi.yaml](../../schema/ws_debugger_request.openapi.yaml) for the request schema.
Check [ws_debugger_response.openapi.yaml](../../schema/we_debugger_response.openapi.yaml) for the response schema.

## Acceptance criteria

- whenever a lambda runtime receives a new request, it sends the WebSocket message that matches the request schema.
- command line tool deserializes the WebSocket message
- the response is also stored in the DynamoDB table PLLDBDebugger. Check the table schema in [REQ-FN-0006](./req_fn_0006.md)

## Out of scope

- handling of the message in the command line tool, just pass it to the Debugger class
- the response is stored by the websocket lambda handler
- make sure that the websocket lambda handler supports the bi-directional communication
- don't add additional modules or packages for lambda handlers, put all new logic and dataclasses there