# PLLDB - Python Lambda Local DeBugger

This project provides a command-line tool that install an infrastructure that allows debugging lambda functions that run on AWS Python runtime locally.

## How to use it?

Run `make init` and `make`.
This will build the project.

You can use `plldb` command to attach to CloudFormation stacks.
Stacks must contains `AWS::Serverless::Function` resources.

To attach to the stack, run `plldb attach --stack-name <stack-name>`.

Then you need to attach a python debugger to the local tool.
In Pycharm this is done by `Attach to Process` action.

In VSCode this is done by `Python Debugger: Remote Attach` launch configuration. Debugpy server must be enabled by adding `--debugpy` argument to the `plldb attach` command. For example:

```bash
plldb attach --stack-name <stack-name> --debugpy
```

You will be given an instruction to create a launch configuration in VSCode.

Then set the breakpoints in the code and start debugging.

You can then wait or invoke lambda functions in AWS and the debugger will break on the breakpoints.

## How to test it?

There is small SAM stack in `tests/test_stack` that can be used to test the tool.

- `cd tests/test_stack`
- `sam build`
- `sam deploy`
- `plldb attach --stack-name plldb-test-stack`
- attach the debugger to the local tool
- go to the AWS Console and invoke the lambda function plldb-test-stack-...

## How does it work?

The tool installs a helper stack that provides WebSocket API that allows this tool to connect to the interface and receive and send messages.
The tool then attaches to existing CloudFormation stack and uses the helper stack to modify the lambda functions. Lambda functions are attached with custom layer that uses AWS_LAMBDA_EXEC_WRAPPER to modify the script that executes the lambda runtime. Custom runtime is used that hooks to AWS Lambda runtime API and intercepts the invocation requests. Instead of passing it to the original code, lambda sends a WebSocket message to debugger session. This is received by the local tool which then finds appropriate code locally and executes it. This allows the local debugger to debug the code. The response is then sent back to the WebSocket API which updates the response in correlation table. This is then picked by the lambda runtime and returned back to the AWS Lambda.

This project tracks all major changes in [requirements](./docs/requirements/). Check them to understand how the tool works and how it evolves.

This project is also entirely managed by agentic coding. It uses Claude to implement all the requirements with minimal human intervention.
KEEP IT AI FIRST!!!

## Issues

Use GitHub issues to report any issues or feature requests.

## Architecture

### Stack

Stack is a CloudFormation stack that contains the helper stack and the lambda functions that orchestrate the necessary infrastructure.

#### PLLDBDebuggerRole

This role is used by the lambda functions and users as well to access the necessary resources. This role has trust policy set so it allows any principal from its AWS account to assume it.

This role grants following permissions:
- Read and Write into PLLDBSessions table
- Read and Write into PLLDBDebugger table
- Send messages to WebSocket API

#### PLLDBManagerRole

This role is used to modify AWS Lambda functions. This is necessary to add AWS_LAMBDA_EXEC_WRAPPER environment variable and also the DEBUGGER_SESSION_ID and DEBUGGER_CONNECTION_ID environment variables. It also allows to attach and detach lambda layers.

This role grants following permissions:
- Read and Write into PLLDBDebugger table
- Attach and detach lambda layers
- Add environment variables to lambda functions

#### PLLDBSessions table

PLLDBSessions is an AWS::DynamoDB::Table that contains the informations about the sessions. See an example of the Session item:

```json
{
  "SessionId": "9ada04b8-639d-476f-af6a-40c89714b812", // this serves as a secret that's shared between the client and the server
  "ConnectionId": "1234567890", // this is the connection id of the WebSocket API that's associated with the session
  "TTL": 1716883200, // this is the expiration time of the session in seconds since epoch
  "Status": "PENDING", // this is the status of the session, allowed values are: PENDING, ACTIVE, CLOSED
  "StackName": "my-stack" // this is the name of the stack that the session is associated with
}
```

When the local tool initiates the debugging session with the stack then it generates a random uuid. This uuid serves as the authorization token for the session.
The local tool uses current AWS IAM credentials to assume PLLDBDebuggerRole and then it creates a new session item in the table. 

New session is "PENDING" and it allows the user to connect to the WebSocket API. Authorizer that's attached to the WebSocket API is used to authorize the connection. The tool sends the session id in the connect request and the authorizer checks that there is a PENDING session with the same session id. If there is, then the connection is authorized. The authorizer also updates the ConnedtionId for the SessionId and TTL for the session and sets the status to ACTIVE.

#### WebSocket API

WebSocket API is used to send and receive debugger messages. 

When the connection is initiated, the tool sends the session id in the query parameter. This is used to authorize the connection. When the connection is initiated, the WebSocket API handler also invokes the manager that modifies the stack that's debugged. This is done under PLLDBManagerRole.

This instrumentation adds the following environment variables to the lambda function:
- DEBUGGER_SESSION_ID - this is the session id that's used to identify the session
- DEBUGGER_CONNECTION_ID - this is the connection id that's used to identify the connection
- AWS_LAMBDA_EXEC_WRAPPER - this is the wrapper that's used to intercept the invocation requests
and it also attaches a custom layer that contains the debugger code.

#### PLLDBDebuggerTable

This table contains records that allow to correlate the requests from the lambda runtime with the responses from the debugger.

```json
{
  "RequestId": "1234567890", // this is the request id that's used to identify the request
  "SessionId": "9ada04b8-639d-476f-af6a-40c89714b812", // this is the session id that's used to identify the session
  "ConnectionId": "1234567890", // this is the connection id that's used to identify the connection
  "Request": "...", // this is the request from the lambda runtime, serialized as JSON string
  "EnvironmentVariables": {}, // this is the environment variables that are set for the lambda function
  "ResponseCode": 200, // this is the response code from the lambda runtime
  "Error": "...", // this is the error from the lambda function, serialized as JSON string
  "Response": "..." // this is the response from the debugger, serialized as JSON string
}
```