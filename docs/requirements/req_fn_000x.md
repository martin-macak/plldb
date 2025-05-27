# REQ_FN_0003: Stack infrastructure for session management

Deploys necessary infrastructure for state management. The infrastructure covers the following resources:

- PLLDBSessions - AWS::DynamoDB::Table for sessions and connections

Also new command `plldb attach --stack-name <stack-name>` is added to the CLI. This command is used to attach the debugger to the stack.

## Resources

These resources are added to `template.yaml` file mamaged by `plldb.bootstrap.cloudformation` package.

### PLLDBSessions - AWS::DynamoDB::Table for sessions and connections

| Attribute    | Type   | Description                                                            |
| ------------ | ------ | ---------------------------------------------------------------------- |
| SessionId    | String | The unique identifier for the session.                                 |
| ConnectionId | String | The unique identifier for the connection.                              |
| TTL          | Number | The expiration time of the session in seconds since epoch.             |
| Status       | String | The status of the session. Allowed values are: PENDING, ACTIVE, CLOSED |
| StackName    | String | The name of the stack that the session is associated with              |

Key:
  - SessionId
Global Secondary Index:
  - GSI-StackName
    Key: 
      - StackName
      - TTL
  - GSI-ConnectionId
    Key:
      - ConnectionId
      - SessionId

### PLLDBManagementAPI

New REST API is added to the stack. This API is used to manage the sessions and connections.

Authorization: AWSIAM for each operation

#### POST /sessions

Creates a new session.
When this operation is invoked, the API creates a new session item in the PLLDBSessions table.

The request body is:
```json
{
  "stackName": "my-stack"
}
```

The response is 201 with the following body:
```json
{
  "sessionId": "1234567890"
}
```

The session is stored in the PLLDBSessions table with the following attributes:
- SessionId = <random-uuid>
- StackName = request.stackName
- TTL = 1 hour
- Status = "PENDING"

The TTL is set to 1 hour.

## Acceptance Criteria

### Command Line Tool

When the `plldb attach --stack-name <stack-name>` command is run, the stack is attached to the debugger.
Use following steps to implement this:

1. The command line tool discovers the REST API endpoint using boto3 api under current AWS IAM credentials.
2. The command line tools makes POST request to /sessions
3. The command line tool receives SessionId in the response.
4. The command line tool discovers WebSocket API endpoint using boto3 api under current AWS IAM credentials.
5. The command line tool creates a new WebSocket connection to the WebSocket API and sends the SessionId in the query parameter.
6. The command line tool enters the loop that waits for the messages from the WebSocket API.

### Backend

- requests for sessions are stored in the PLLDBSessions table.
- WebSocket connections are authorized by lambda authorizer.
- Lambda authorizer checks the sessionId in the query parameter. It checks that there is a PENDING session with the same sessionId in PLLDBSessions table.
- When the connection is authorized, the connectionId is set for the session and the status is set to ACTIVE.
- When the connection is closed, the connectionId is set to null and the status is set to CLOSED.
