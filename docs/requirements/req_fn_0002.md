# REQ_FN_0002: Bootstrap the infrastructure stack

When the `plldb bootstrap` command is run, it will also deploy the CloudFormation stack for the infrastructure stack.

## Acceptance Criteria

- when `plldb bootstrap setup` is run, it will deploy the CloudFormation stack for the infrastructure stack.
- the stack is vanilla CloudFormation stack, no Serverless transformations are used.
- deployed resources are:
  - PLDDBSessions : AWS::DynamoDB::Table
  - PLLDBDebugger : AWS::DynamoDB::Table
  - PLLDBDebuggerRole : AWS::IAM::Role
  - PLLDBManagerRole : AWS::IAM::Role
  - PLDDBAPI : AWS::ApiGatewayV2::Api

### PLDDBSessions

PLLDBSessions is a DynamoDB table that contains the informations about the sessions.
It must have following properties:
- SessionId : string
- ConnectionId : string
- StackName : string

Primary key: SessionId
Secondary indexes:
- ConnectionId : string
  - Partition key: ConnectionId
  - Sort key: SessionId
- StackName : string
  - Partition key: StackName
  - Sort key: ConnectionId

### PLLDBDebugger

PLLDBDebugger is a DynamoDB table that contains the informations about the debugger.
It must have following properties:
- RequestId : string

Primary key: RequestId

### PLLDBAPI

This is a WebSocket API that's used to communicate with the debugger.

- API uses custom lambda authorizer
- Lambda authorizer expectects that client sends sessionId as query parameter. The sessionId is used to identify the session. If the sessionId is found in PLLDBSessions table, the authorizer authorizes the request. The connectionId is updated to the sessionId record.

## Implementation Notes

- the stack definition is in the `plldb.bootstrap.cloudformation` package.
- template is named `template.yaml` and contains all stack resources.
- all lambda functions are in the `plldb.bootstrap.cloudformation.lambda_functions` package.
- lambda functions are not inlined, they are included from `plldb.bootstrap.cloudformation.lambda_functions` package.
- the stack is deployed by boto3 cloudformation client.
- the stack is deployed from the `plldb.core.bootstrap.cloudformation` package location.
