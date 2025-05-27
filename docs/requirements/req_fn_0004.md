# REQ-FN-0004: Authorization for WebSocket connections

Adds authorization for WebSocket connections.
Whenever a WebSocket connection is established, the client must provide a valid session id in the connection. This is provided in the query params as sessionId.
The sessionId is first obtained from the REST API that uses AWS IAM for authorization.
The authorizer checks that the sessionId is valid and that the session is PENDING.
Sessions can be used only once.

This task is a follow up to [REQ-FN-0003](./req_fn_0003.md) and [REQ-FN-0002](./req_fn_0002.md)

## Acceptance Criteria

- authorizer for WebSocket connections is implemented so it uses sessionId from the query param
- if the sessionId does not exist in in then PLLDBSessions table then the connection is rejected
- it the session is not PENDING then the connection is rejected
- once the connection is established, the session is updated to ACTIVE and ConnectionId is set to the connection id
