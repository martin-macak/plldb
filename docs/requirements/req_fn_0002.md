# REQ_FN_0002: Bootstrap the infrastructure stack

When the `plldb bootstrap` command is run, it will also deploy the CloudFormation stack for the infrastructure stack.

## Acceptance Criteria

- the deployment is capable of packaging lambda functions into zip files.
- the packaged lambda functions are uploaded to the s3 bucket that was created in [REQ_FN_0001](./req_fn_0001.md) ticket.
- the packaged lambda functions use prefix that uses the `plldb` package version. for example `plldb/versions/0.1.0/lambda_functions/<function_name>.zip`
- the template.yaml is updated with the reference to the packaged lambda functions.
- the packaged template.yaml is uploaded to the s3 bucket that was created in [REQ_FN_0001](./req_fn_0001.md) ticket.
- the packaged template.yaml uses prefix that uses the `plldb` package version. for example `plldb/versions/0.1.0/template.yaml`
- the packaged template is installed as a CloudFormation stack
- the stack name is `plldb`
- the deployment is run when `plldb bootstrap setup` command is run.
- when the `plldb bootstrap destroy` command is run, the stack is destroyed. packaged lambda functions are not deleted.
- the progress of the packaging anddeployment is displayed to the user.

### Stack resources

#### PLLDBServiceRole - Service Role

- Service Role is created.
- Role is used by the stack resources like lambda functions.

#### PLLDBAPI - WebSocket API

- WebSocket API is created
- WebSocket API handles connect, disconnect, authorize and default messages.
- Each message is handled by a separate lambda function. Check [Implementation notes](#implementation-notes) section for more details.

### Out of scope

- implementation of lambda functions. the lambda functions don't contain any implementation except from the default lambda handler.

## Implementation notes

- the `template.yaml` is located in the `plldb.cloudformation` package.
- the lambda functions are located in the `plldb.cloudformation.lambda_functions` package.
- the packaging function is implemented in `plldb.setup.BootstrapManager` class.
