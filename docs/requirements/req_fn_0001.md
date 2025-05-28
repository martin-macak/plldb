# REQ_FN_0001: Bootstrap the core infrastructure

Bootstraps the S3 bucket for the core infrastructure.
New command `plldb bootstrap` is added to the CLI. This command runs with two sub-commands:
- `plldb bootstrap setup` - creates the S3 bucket and uploads the core infrastructure to it.
- `plldb bootstrap destroy` - destroys the S3 bucket and removes the core infrastructure.
The `setup` sub-command is the default command, so if `plldb bootstrap` is run without any sub-command, it will run the `setup` sub-command.

## Acceptance Criteria

- when `plldb bootstrap` is run without any sub-command, it will run the `setup` sub-command.
- when `plldb bootstrap setup` is run, it will create the S3 bucket and upload the core infrastructure to it.
- the bucket must be named like `plldb-core-infrastructure-<region>-<account-id>`.
- the s3 bucket must not have public access.
- when the bucket already exists, it will not be recreated.
- when the `destroy` sub-command is run, it will destroy the S3 bucket and remove the core infrastructure.
- when the `destroy` sub-command is run and the bucket does not exist, it will not fail.
- both operations are idempotent.
- commands log properly there progress.

## Implementation Notes

- don't put the logic in the CLI commands
- use `plldb.cloudformation` package.
- put the logic for setup and destroy in the `plldb.setup` module.
- put tests for the packages in `plldb` package into separate directories in `tests`. for example `tests/test_setup.py` should be used to test the `plldb.setup` module.
- prefer using `mock_aws_session` fixture from `tests/conftest.py` to mock the AWS session and AWS resources. this helps to validate calls because moto validates client calls.