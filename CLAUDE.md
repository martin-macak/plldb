# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development Setup
```bash
make init    # Install dependencies using uv
```

### Testing
```bash
make test    # Run all tests with pytest
uv run pytest tests/test_example.py::TestAWSResources::test_dynamodb_table -v    # Run a single test
uv run pytest tests/    # Run all tests
```

### Code Quality
```bash
make pyright    # Type checking
make format     # Format code with ruff
make clean      # Clean build artifacts and cache
```

### Building
```bash
make build    # Build distribution packages
```

## Architecture

**plldb** (Python Lambda Local DeBugger) is a CLI tool that enables local debugging of AWS Lambda functions by installing infrastructure that intercepts Lambda invocations via WebSocket API.

### How It Works

The tool installs a helper CloudFormation stack that provides:
1. **WebSocket API** - Receives/sends messages between Lambda and local debugger
2. **Custom Lambda Layer** - Uses AWS_LAMBDA_EXEC_WRAPPER to intercept invocation requests
3. **DynamoDB Tables** - PLLDBSessions and PLLDBDebugger for session management and request correlation
4. **IAM Roles** - PLLDBDebuggerRole and PLLDBManagerRole for controlled access

When debugging:
1. Local tool generates session UUID as auth token
2. Tool assumes PLLDBDebuggerRole and creates PENDING session in DynamoDB
3. WebSocket connection authorized via session ID
4. Lambda functions modified with environment variables (_DEBUGGER_SESSION_ID_, _DEBUGGER_CONNECTION_ID_)
5. Invocations intercepted and sent to local debugger via WebSocket
6. Local debugger executes code and returns response

### Code Structure

The project is built with:
- **boto3** for AWS SDK functionality
- **click** for command-line interface
- **moto** for safe AWS service mocking during tests

The codebase follows a modular architecture:
- `plldb.cli` - Main CLI entry point using Click framework
- `plldb.setup` - Infrastructure setup module for Lambda debugging
- Core functionality is separated from CLI for better testability

The project uses modern Python tooling:
- **uv** as the package manager (not pip/poetry)
- **hatchling** as the build backend
- **pyright** for type checking with `.venv` in project root
- **ruff** for linting (E/F/I rules, 200-char line length)
- **Python 3.13+** required

## Testing Approach

Tests use the `mock_aws_session` fixture from `tests/conftest.py` which:
1. Isolates AWS environment variables
2. Removes AWS_PROFILE to prevent real AWS access
3. Provides a mocked boto3 session

This ensures all AWS operations during testing are safely mocked and will never touch real AWS resources.

- Use `monkeypatch` fixture instead of `unittest.mock.patch`.

## Core Components

### Infrastructure Management (`plldb.setup.BootstrapManager`)
Handles the complete infrastructure setup:
- Creates S3 bucket for Lambda deployment artifacts
- Packages and uploads Lambda functions from `cloudformation/lambda_functions/`
- Packages Lambda layer with custom runtime wrapper
- Deploys CloudFormation stack with all resources

### Session Management
- **Stack Discovery** (`plldb.stack_discovery`) - Discovers WebSocket and REST API endpoints from deployed stacks
- **REST Client** (`plldb.rest_client`) - Creates debug sessions with SigV4 authentication
- **WebSocket Client** (`plldb.websocket_client`) - Maintains debugging connection

### Lambda Layer Runtime
The custom layer (`cloudformation/layer/`) intercepts Lambda invocations:
- `bootstrap` shell script sets up AWS_LAMBDA_EXEC_WRAPPER
- `lambda_runtime.py` checks for debug environment variables
- Routes invocations through WebSocket when debugging is enabled

## CLI Commands

The main entry point is `plldb` which provides:
- `plldb bootstrap` - Set up debugging infrastructure
- `plldb bootstrap destroy` - Tear down debugging infrastructure  
- `plldb attach` - Attach debugger to a CloudFormation stack

## Important Files

- `cloudformation/template.yaml` - Complete infrastructure definition
- `pyproject.toml` - Project configuration with tool settings
- `tests/conftest.py` - Core testing fixtures including `mock_aws_session`