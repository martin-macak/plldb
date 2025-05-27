# PLLDB - Python Lambda Local DeBugger

This project provides a command-line tool that install an infrastructure that allows debugging lambda functions that run on AWS Python runtime locally.

## How does it work?

The tool installs a helper stack that provides WebSocket API that allows this tool to connect to the interface and receive and send messages.
The tool then attaches to existing CloudFormation stack and uses the helper stack to modify the lambda functions. Lambda functions are attached with custom layer that uses AWS_LAMBDA_EXEC_WRAPPER to modify the script that executes the lambda runtime. Custom runtime is used that hooks to AWS Lambda runtime API and intercepts the invocation requests. Instead of passing it to the original code, lambda sends a WebSocket message to debugger session. This is received by the local tool which then finds appropriate code locally and executes it. This allows the local debugger to debug the code. The response is then sent back to the WebSocket API which updates the response in correlation table. This is then picked by the lambda runtime and returned back to the AWS Lambda.