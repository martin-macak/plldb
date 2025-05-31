# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow Guidelines

- When fixing github issues, always create new branch for it, called issue/gh-<issue-id>
- Before committing, run `make format` to format codebase
- Pre-commit hooks are configured to run `make format`, `make pyright`, and `make test` automatically
- Always link fixed GH issue into PR

## Commands

### Development Setup
```bash
make init    # Install dependencies using uv and clean up old installations
make         # Equivalent to make init && make build
```

### Testing
```bash
make test    # Run all tests with pytest
uv run pytest tests/test_example.py::TestAWSResources::test_dynamodb_table -v    # Run a single test
uv run pytest tests/ -k "test_name"    # Run tests matching pattern
uv run pytest tests/ -x    # Stop on first failure
```

### Code Quality
```bash
make pyright    # Type checking
make format     # Format code with ruff
make clean      # Clean build artifacts and cache
```

### Building
```bash
make build    # Build distribution packages (runs init first)
```

### GitHub Interactions
```bash
gh pr list    # List pull requests
gh issue create    # Create a new issue
gh pr create    # Create a pull request
```

### Local Debugging
```bash
plldb bootstrap    # Set up debugging infrastructure
plldb bootstrap destroy    # Tear down debugging infrastructure
plldb attach --stack-name <stack-name>    # Attach debugger to a CloudFormation stack
plldb attach --stack-name <stack-name> --debugpy    # Enable debugpy for VSCode debugging
```

## Architecture

**plldb** (Python Lambda Local DeBugger) is a CLI tool that enables local debugging of AWS Lambda functions by installing infrastructure that intercepts Lambda invocations via WebSocket API.

### How It Works

The tool installs a helper CloudFormation stack that provides:
1. **WebSocket API** - Receives/sends messages between Lambda and local debugger
2. **Custom Lambda Layer** - Uses AWS_LAMBDA_EXEC_WRAPPER to intercept invocation requests
3. **DynamoDB Tables** - PLLDBSessions and PLLDBDebugger for session management and request correlation
4. **IAM Roles** - PLLDBDebuggerRole and PLLDBManagerRole for controlled access
5. **REST API** - For session creation with SigV4 authentication

When debugging:
1. Local tool generates session UUID as auth token
2. Tool assumes PLLDBDebuggerRole and creates PENDING session in DynamoDB
3. WebSocket connection authorized via session ID
4. Lambda functions modified with environment variables (DEBUGGER_SESSION_ID, DEBUGGER_CONNECTION_ID, AWS_LAMBDA_EXEC_WRAPPER)
5. Invocations intercepted and sent to local debugger via WebSocket
6. Local debugger executes code and returns response
7. Response sent back via DynamoDB correlation table

### Code Structure

The project is built with:
- **boto3** for AWS SDK functionality
- **click** for command-line interface  
- **moto** for safe AWS service mocking during tests
- **websocket-client** for WebSocket connections
- **debugpy** for VSCode debugging integration (optional)

The codebase follows a modular architecture:
- `plldb.cli` - Main CLI entry point using Click framework
- `plldb.setup` - Infrastructure setup module (BootstrapManager)
- `plldb.debugger` - Core debugging functionality
- `plldb.executor` - Local code execution engine
- `plldb.protocol` - Message protocol definitions
- `plldb.simulator` - Local Lambda simulation for testing
- Core functionality is separated from CLI for better testability

The project uses modern Python tooling:
- **uv** as the package manager (not pip/poetry)
- **hatchling** as the build backend
- **pyright** for type checking with `.venv` in project root
- **ruff** for linting (E/F/I rules, 200-char line length)
- **Python 3.13+** required
- **pre-commit** hooks configured for quality checks

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
- `lambda_runtime.py` checks for debug environment variables (DEBUGGER_SESSION_ID, DEBUGGER_CONNECTION_ID)
- Routes invocations through WebSocket when debugging is enabled
- Uses `send_debugger_request()` to forward invocations to local debugger
- Polls DynamoDB for debugger response

### Debugging Flow
1. Lambda invocation intercepted by custom runtime
2. Request stored in PLLDBDebugger DynamoDB table
3. WebSocket message sent to local debugger with invocation details
4. Local debugger executes handler code in simulated environment
5. Response written back to DynamoDB
6. Lambda runtime polls and retrieves response
7. Response returned to Lambda service

## CLI Commands

The main entry point is `plldb` which provides:
- `plldb bootstrap` - Set up debugging infrastructure
- `plldb bootstrap destroy` - Tear down debugging infrastructure  
- `plldb attach` - Attach debugger to a CloudFormation stack
- `plldb simulate` - Run local simulation for testing

## Important Files

- `cloudformation/template.yaml` - Complete infrastructure definition
- `pyproject.toml` - Project configuration with tool settings
- `tests/conftest.py` - Core testing fixtures including `mock_aws_session`
- `.pre-commit-config.yaml` - Pre-commit hooks configuration