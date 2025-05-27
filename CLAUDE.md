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
pytest tests/test_example.py::test_dynamodb_operations -v    # Run a single test
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

The project is built with:
- **boto3** for AWS SDK functionality
- **click** for command-line interface
- **moto** for safe AWS service mocking during tests

The codebase follows a modular architecture:
- `plldb.cli` - Main CLI entry point using Click framework
- `plldb.bootstrap` - Infrastructure setup module for Lambda debugging
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