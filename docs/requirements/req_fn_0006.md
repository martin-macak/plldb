# REQ-FN-0006: Debugger role and Request Table

New role for the debugger lambda functions and new table for requests.

## Resources

- PLLDBDebuggerRole - AWS::IAM::Role for the role assumed by the debugger lambda functions
- PLLDBDebugger - AWS::DynamoDB::Table for debugger requests and responses

### PLLDBDebugger - AWS::DynamoDB::Table for debugger requests and responses

| Attribute            | Type       | Description                                        |
| -------------------- | ---------- | -------------------------------------------------- |
| RequestId            | String     | The unique identifier for the request.             |
| SessionId            | String     | The unique identifier for the session.             |
| ConnectionId         | String     | The unique identifier for the connection.          |
| Request              | String     | The serialized request as JSON string.             |
| Response             | String     | The serialized response as JSON string.            |
| StatusCode           | Number     | The HTTP status code of the response.              |
| ErrorMessage         | String     | The error message if the request failed.           |
| EnvironmentVariables | Dictionary | The environment variables as key/value dictionary. |

Key:
  - RequestId
Global Secondary Index:
  - GSI-SessionId
    Key: 
      - SessionId
      - RequestId
  - GSI-ConnectionId
    Key: 
      - ConnectionId
      - RequestId

### PLLDBDebuggerRole - AWS::IAM::Role for the role assumed by the debugger lambda functions

This role can be assumed by any lambda function in current AWS account.
This role can read and write to the PLLDBDebuggerTable table.
This role can send messages to the PLLDBWebSocket API.

## Acceptance Criteria

- New resources are created