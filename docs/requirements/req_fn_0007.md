# REQ-FN-0007: Lambda layer with debugger runtime

Create a lambda layer that can override default python runtime.
According to [AWS Lambda Runtime API](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-api.html), the runtime can be overridden by setting the `AWS_LAMBDA_EXEC_WRAPPER` environment variable.

This layer delivers custom python scripts that register to the Lambda Runtime API. Instead of calling the lambda handler, this runtime checks if the DEBUGGER_SESSION_ID and DEBUGGER_CONNECTION_ID environment variables are set. If they are, it will engage with the debugger.

To do so, it assumes the PLLDBDebuggerRole role. Under this role, it sends a message to the PLLDBWebSocket API. This message contains the environment variables and serialized request. Then it starts a polling loop that waits for the response from the debugger. If the item with the RequestId is updated and the loop detects that the ResponseCode is not empty, then it returns the response to the AWS Lambda Runtime API.

## New layer

New layer is created in `plldb/bootstrap/cloudformation/layer/` directory.

It must follow specification provided in [Modify the runtime](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-modify.html).

This layer must execute the `lambda_runtime.py` script that registers to the Lambda Runtime API.

All actions performed in the layer muse be performed under LLDBDebuggerRole role.

## Acceptance Criteria

- Layer code is implemented in `plldb/bootstrap/cloudformation/layer/` directory
- Layer code follows the specifications required by the AWS Lambda Runtime API so 
  - it registers to the Lambda Runtime API
  - when the event is received, it creates a new item in the PLLDBDebugger table with. Check the table schema in [REQ-FN-0006](./req_fn_0006.md)
  - it starts a polling loop that waits for the response from the debugger
  - when the response is received, it updates the item in the PLLDBDebugger table with the response
- the response code is returned to the AWS Lambda Runtime API
- the response is returned to the AWS Lambda Runtime API
- if the error is set in the item then the error is returned to the AWS Lambda Runtime API