# REQ-FN-0003: Management API

New API for managing the sessions and connections.

## Resources

- PLLDBAPI - AWS::ApiGateway::RestApi for the management API
- PLLDBSessions - AWS::DynamoDB::Table for sessions and connections

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

### PLLDBAPI Operations

#### POST /sessions : Create a new session

Request body:
```json
{
  "stackName": "my-stack"
}
```

Response body (201):
```json
{
    "sessionId": "1234567890"
}
```

This operation creates a new session in the PLLDBSessions table. The item is created with the following attributes:
- SessionId = <random-uuid>
- StackName = request.stackName
- TTL = 1 hour
- Status = "PENDING"

The TTL is set to 1 hour.

### Acceptance Criteria

- new resources are added to the stack
- api id is exposed as an output in CloudFormation template
- REST API uses AWS IAM for authorization for all operations

## Development Notes

- `restapi.py` lambda handler is created in `plldb.cloudformation.lambda_functions` package.
- `restapi.py` lambda handler is used to handle all operations of the REST API.