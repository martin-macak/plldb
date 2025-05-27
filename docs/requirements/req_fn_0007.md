# REQ-FN-0007: Lambda layer with debugger runtime

Create a lambda layer that can override default python runtime.
According to [AWS Lambda Runtime API](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-api.html), the runtime can be overridden by setting the `AWS_LAMBDA_EXEC_WRAPPER` environment variable.

This layer delivers custom python scripts that register to the Lambda Runtime API. Instead of calling the lambda handler, this runtime checks if the _DEBUGGER_SESSION_ID_ and _DEBUGGER_CONNECTION_ID_ environment variables are set. If they are, it will engage with the debugger.

To do so, it assumes the PLLDBDebuggerRole role. Under this role, it sends a message to the PLLDBWebSocket API. This message contains the environment variables and serialized request. Then it starts a polling loop that waits for the response from the debugger. This response is stored in the PLLDBDebuggerTable table with corresponding RequestId.