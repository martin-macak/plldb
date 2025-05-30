.PHONY: init build test clean publish

all: init build

# Initialize development environment
init:
	rm -rf .venv/lib/python3.13/site-packages/plldb-*
	uv sync --dev --no-cache

# Build the package
build: init
	uv build

# Run tests
test:
	uv run pytest tests/

pyright:
	uv run pyright

format:
	uv run ruff format

# Publish to PyPI
publish: build
	uv publish

# Clean up build artifacts and cache files
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} + 