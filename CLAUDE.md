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
make clean      # Clean build artifacts and cache
```

### Building
```bash
make build    # Build distribution packages
```

## Architecture

**plldb** is a Python CLI tool for AWS operations built with:
- **boto3** for AWS SDK functionality
- **click** for command-line interface
- **moto** for safe AWS service mocking during tests

The project uses modern Python tooling:
- **uv** as the package manager (not pip/poetry)
- **hatchling** as the build backend
- **pyright** for type checking with `.venv` in project root
- **ruff** for linting (E/F/I rules, 88-char lines)

## Testing Approach

Tests use the `mock_aws_session` fixture from `tests/conftest.py` which:
1. Isolates AWS environment variables
2. Removes AWS_PROFILE to prevent real AWS access
3. Provides a mocked boto3 session

This ensures all AWS operations during testing are safely mocked and will never touch real AWS resources.