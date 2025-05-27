# REQ_FN_0002: Bootstrap the infrastructure stack

When the `plldb bootstrap` command is run, it will also deploy the CloudFormation stack for the infrastructure stack.

## Acceptance Criteria

- when `plldb bootstrap setup` is run, it will deploy the CloudFormation stack for the infrastructure stack.
- when the `plldb bootstrap destroy` is run, it will destroy the CloudFormation stack for the infrastructure stack.
- the stack is deployed without any parameters.
- the stack is deployed without any errors.
- the stack is packaged to the bucket that was created in [REQ_FN_0001](./req_fn_0001.md) ticket.
- the lambda function code is packaged to the bucket that was created in [REQ_FN_0001](./req_fn_0001.md) ticket.
- the stack is named `plldb`.
- the stack is vanilla CloudFormation stack, no Serverless transformations are used.
- deployed resources are:
  - PLDDBSessions : AWS::DynamoDB::Table
  - PLLDBDebugger : AWS::DynamoDB::Table
  - PLLDBDebuggerRole : AWS::IAM::Role
  - PLLDBManagerRole : AWS::IAM::Role
  - PLDDBAPI : AWS::ApiGatewayV2::Api
- the stack is deployed under current AWS account and current users AWS IAM credentials.

See the [stack definition](#stack-definition) section for more details.

## Out of scope

- the lambda functions for WebSocket API authorizer, connect, disconnect and default handlers are created but no implementation is provided in this ticket.
- the API authorizer is implement to authorize all requests.
- no database management is implemented in this ticket.

## Stack definition

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

Expected lambda function structure:
```
/plldb/bootstrap/cloudformation/lambda_functions/
├── ws_api_connect_handler.py
├── ws_api_disconnect_handler.py
├── ws_api_authorize_handler.py
└── ws_api_default_handler.py
```

## Implementation Notes

Use the phased deployment approach:
- Package lambda functions into zip files.
- Upload packaged lambda functions to s3 bucket.
- Modify the template.yaml to reference the packaged lambda functions.
- Deploy the stack.

Follow these rules:
- the stack definition is in the `plldb.bootstrap.cloudformation` package.
- create lambda function for connect, disconnect, authorize and default handlers. for example `ws_api_connect_handler.py` for connect handler.
- template is named `template.yaml` and contains all stack resources.
- all lambda functions are in the `plldb.bootstrap.cloudformation.lambda_functions` package.
- lambda functions MUST NOT be inlined, they are included from `plldb.bootstrap.cloudformation.lambda_functions` package and packaged into s3 bucket.
- the stack is deployed by boto3 cloudformation client.
- the stack is deployed from the `plldb.core.bootstrap.cloudformation` package location.
- the packaging uses prefix that matches the version on the `plldb` package. for example `plldb/versions/0.1.0/lambda_functions/<function_name>.zip`
- the packaging mechanism properly handles placeholders in the template.yaml.
