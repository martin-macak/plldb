import os
import sys
from pathlib import Path
import pytest
from unittest.mock import Mock, patch
import tempfile
import shutil
from plldb.executor import (
    Executor,
    LambdaFunctionNotFoundError,
    LambdaFunctionNotAServerlessFunctionError,
)


class TestExecutor:
    """Test cases for the Executor class."""

    def test_init_default_paths(self):
        """Test Executor initialization with default paths."""
        with patch("os.getcwd", return_value="/test/path"):
            executor = Executor()
            assert executor.working_dir == Path("/test/path")
            assert executor.cfn_template_path == Path("/test/path/template.yaml")

    def test_init_custom_paths(self):
        """Test Executor initialization with custom paths."""
        executor = Executor(working_dir="/custom/path", cfn_template_path="/custom/template.yaml")
        assert executor.working_dir == "/custom/path"
        assert executor.cfn_template_path == "/custom/template.yaml"

    def test_init_path_objects(self):
        """Test Executor initialization with Path objects."""
        executor = Executor(
            working_dir=Path("/custom/path"),
            cfn_template_path=Path("/custom/template.yaml"),
        )
        assert executor.working_dir == Path("/custom/path")
        assert executor.cfn_template_path == Path("/custom/template.yaml")


class TestWithSitePackages:
    """Test cases for with_site_packages context manager."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def create_venv_structure(self, base_path, venv_name, platform="unix"):
        """Helper to create virtual environment directory structure."""
        venv_path = Path(base_path) / venv_name

        if platform == "win32":
            lib_path = venv_path / "Lib"
            site_packages = lib_path / "site-packages"
        else:
            lib_path = venv_path / "lib" / "python3.9"
            site_packages = lib_path / "site-packages"

        site_packages.mkdir(parents=True)
        return venv_path, site_packages

    def test_with_site_packages_no_venv(self, temp_dir):
        """Test with_site_packages when no virtual environment exists."""
        executor = Executor(working_dir=temp_dir)

        original_sys_path = sys.path.copy()
        original_pythonpath = os.environ.get("PYTHONPATH", "")

        with executor.with_site_packages():
            # sys.path should remain unchanged
            assert sys.path == original_sys_path
            # PYTHONPATH should remain unchanged
            assert os.environ.get("PYTHONPATH", "") == original_pythonpath

    def test_with_site_packages_unix_venv(self, temp_dir, monkeypatch):
        """Test with_site_packages with Unix-style virtual environment."""
        monkeypatch.setattr(sys, "platform", "linux")

        # Create .venv structure
        venv_path, site_packages = self.create_venv_structure(temp_dir, ".venv", "unix")

        executor = Executor(working_dir=temp_dir)

        original_sys_path = sys.path.copy()
        original_pythonpath = os.environ.get("PYTHONPATH", "")

        with executor.with_site_packages():
            # site-packages should be added to sys.path
            assert str(site_packages) in sys.path
            assert sys.path[0] == str(site_packages)

            # PYTHONPATH should contain site-packages
            pythonpath = os.environ.get("PYTHONPATH", "")
            assert str(site_packages) in pythonpath

        # After context, everything should be restored
        assert sys.path == original_sys_path
        assert os.environ.get("PYTHONPATH", "") == original_pythonpath

    def test_with_site_packages_windows_venv(self, temp_dir, monkeypatch):
        """Test with_site_packages with Windows-style virtual environment."""
        monkeypatch.setattr(sys, "platform", "win32")

        # Create venv structure
        venv_path, site_packages = self.create_venv_structure(temp_dir, "venv", "win32")

        executor = Executor(working_dir=temp_dir)

        with executor.with_site_packages():
            assert str(site_packages) in sys.path

    def test_with_site_packages_multiple_venv_candidates(self, temp_dir, monkeypatch):
        """Test with_site_packages when multiple venv candidates exist."""
        monkeypatch.setattr(sys, "platform", "linux")

        # Create multiple venv candidates
        venv1, site1 = self.create_venv_structure(temp_dir, ".venv", "unix")
        venv2, site2 = self.create_venv_structure(temp_dir, "venv", "unix")

        executor = Executor(working_dir=temp_dir)

        with executor.with_site_packages():
            # Should use the first valid one (.venv)
            assert str(site1) in sys.path
            assert str(site2) not in sys.path

    def test_with_site_packages_existing_pythonpath(self, temp_dir, monkeypatch):
        """Test with_site_packages with existing PYTHONPATH."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("PYTHONPATH", "/existing/path")

        venv_path, site_packages = self.create_venv_structure(temp_dir, ".venv", "unix")

        executor = Executor(working_dir=temp_dir)

        with executor.with_site_packages():
            pythonpath = os.environ.get("PYTHONPATH", "")
            assert str(site_packages) in pythonpath
            assert "/existing/path" in pythonpath
            assert pythonpath.startswith(str(site_packages))

        # Should restore original PYTHONPATH
        assert os.environ.get("PYTHONPATH") == "/existing/path"

    def test_with_site_packages_invalid_venv(self, temp_dir):
        """Test with_site_packages with invalid virtual environment structure."""
        # Create directory that looks like venv but isn't
        fake_venv = Path(temp_dir) / ".venv"
        fake_venv.mkdir()
        # Don't create lib directory

        executor = Executor(working_dir=temp_dir)

        original_sys_path = sys.path.copy()

        with executor.with_site_packages():
            # Should not modify sys.path
            assert sys.path == original_sys_path

    def test_with_site_packages_exception_handling(self, temp_dir, monkeypatch):
        """Test with_site_packages properly restores state on exception."""
        monkeypatch.setattr(sys, "platform", "linux")

        venv_path, site_packages = self.create_venv_structure(temp_dir, ".venv", "unix")

        executor = Executor(working_dir=temp_dir)

        original_sys_path = sys.path.copy()
        original_pythonpath = os.environ.get("PYTHONPATH", "")

        with pytest.raises(RuntimeError):
            with executor.with_site_packages():
                assert str(site_packages) in sys.path
                raise RuntimeError("Test exception")

        # State should be restored despite exception
        assert sys.path == original_sys_path
        assert os.environ.get("PYTHONPATH", "") == original_pythonpath


class TestWithLambdaHandler:
    """Test cases for with_lambda_handler context manager."""

    @pytest.fixture
    def mock_cfn_template(self):
        """Create a mock CloudFormation template."""
        return {
            "Resources": {
                "MyLambda": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "lambda_code", "Handler": "app.lambda_handler"}},
                "NotALambda": {"Type": "AWS::S3::Bucket", "Properties": {}},
            }
        }

    @pytest.fixture
    def temp_lambda_code(self, tmp_path):
        """Create temporary lambda code structure."""
        lambda_dir = tmp_path / "lambda_code"
        lambda_dir.mkdir()

        # Create app.py with lambda_handler
        app_py = lambda_dir / "app.py"
        app_py.write_text("""
def lambda_handler(event, context):
    return {"statusCode": 200, "body": "Hello from Lambda"}

def other_function():
    return "Other"
""")

        return tmp_path, lambda_dir

    def test_with_lambda_handler_success(self, mock_cfn_template, temp_lambda_code, monkeypatch):
        """Test successful lambda handler loading."""
        working_dir, lambda_dir = temp_lambda_code

        executor = Executor(working_dir=working_dir)

        # Mock load_cfn_template
        monkeypatch.setattr(executor, "load_cfn_template", lambda: mock_cfn_template)

        with executor.with_lambda_handler("MyLambda") as handler:
            assert callable(handler)
            assert handler.__name__ == "lambda_handler"

            # Test the handler works
            result = handler({"test": "event"}, None)
            assert result["statusCode"] == 200

        # Module should be cleaned up
        assert "app" not in sys.modules

    def test_with_lambda_handler_not_found(self, mock_cfn_template, monkeypatch):
        """Test with_lambda_handler with non-existent Lambda function."""
        executor = Executor()
        monkeypatch.setattr(executor, "load_cfn_template", lambda: mock_cfn_template)

        with pytest.raises(LambdaFunctionNotFoundError) as exc_info:
            with executor.with_lambda_handler("NonExistentLambda"):
                pass

        assert "NonExistentLambda" in str(exc_info.value)

    def test_with_lambda_handler_not_serverless_function(self, mock_cfn_template, monkeypatch):
        """Test with_lambda_handler with non-Lambda resource."""
        executor = Executor()
        monkeypatch.setattr(executor, "load_cfn_template", lambda: mock_cfn_template)

        with pytest.raises(LambdaFunctionNotAServerlessFunctionError) as exc_info:
            with executor.with_lambda_handler("NotALambda"):
                pass

        assert "NotALambda" in str(exc_info.value)

    def test_with_lambda_handler_invalid_handler_format(self, mock_cfn_template, monkeypatch):
        """Test with_lambda_handler with invalid handler format."""
        # Modify template to have invalid handler
        mock_cfn_template["Resources"]["MyLambda"]["Properties"]["Handler"] = "invalid_handler"

        executor = Executor()
        monkeypatch.setattr(executor, "load_cfn_template", lambda: mock_cfn_template)

        with pytest.raises(ValueError) as exc_info:
            with executor.with_lambda_handler("MyLambda"):
                pass

        assert "Invalid handler format" in str(exc_info.value)

    def test_with_lambda_handler_default_code_uri(self, temp_lambda_code, monkeypatch):
        """Test with_lambda_handler with default CodeUri."""
        working_dir, _ = temp_lambda_code

        # Create app.py in working directory
        app_py = working_dir / "app.py"
        app_py.write_text("""
def lambda_handler(event, context):
    return {"statusCode": 201, "body": "Default location"}
""")

        template = {
            "Resources": {
                "MyLambda": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        # No CodeUri specified, should default to "."
                        "Handler": "app.lambda_handler"
                    },
                }
            }
        }

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: template)

        with executor.with_lambda_handler("MyLambda") as handler:
            result = handler({}, None)
            assert result["statusCode"] == 201

    def test_with_lambda_handler_nested_module(self, temp_lambda_code, monkeypatch):
        """Test with_lambda_handler with nested module path."""
        working_dir, lambda_dir = temp_lambda_code

        # Create nested module structure
        nested_dir = lambda_dir / "handlers"
        nested_dir.mkdir()
        (nested_dir / "__init__.py").touch()

        nested_py = nested_dir / "user.py"
        nested_py.write_text("""
def create_user(event, context):
    return {"statusCode": 201, "body": "User created"}
""")

        template = {"Resources": {"CreateUserLambda": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "lambda_code", "Handler": "handlers.user.create_user"}}}}

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: template)

        with executor.with_lambda_handler("CreateUserLambda") as handler:
            assert handler.__name__ == "create_user"
            result = handler({}, None)
            assert result["statusCode"] == 201

    def test_with_lambda_handler_exception_cleanup(self, mock_cfn_template, temp_lambda_code, monkeypatch):
        """Test with_lambda_handler cleans up on exception."""
        working_dir, lambda_dir = temp_lambda_code

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: mock_cfn_template)

        original_sys_path = sys.path.copy()

        with pytest.raises(RuntimeError):
            with executor.with_lambda_handler("MyLambda") as handler:
                assert "app" in sys.modules
                raise RuntimeError("Test exception")

        # Cleanup should still happen
        assert sys.path == original_sys_path
        assert "app" not in sys.modules

    def test_with_lambda_handler_missing_handler_function(self, temp_lambda_code, monkeypatch):
        """Test with_lambda_handler when handler function doesn't exist in module."""
        working_dir, lambda_dir = temp_lambda_code

        # Create module without the expected handler
        bad_app = lambda_dir / "bad_app.py"
        bad_app.write_text("""
def some_other_function():
    return "Not a handler"
""")

        template = {"Resources": {"BadLambda": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "lambda_code", "Handler": "bad_app.missing_handler"}}}}

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: template)

        with pytest.raises(AttributeError):
            with executor.with_lambda_handler("BadLambda"):
                pass


class TestLoadCfnTemplate:
    """Test cases for load_cfn_template method."""

    def test_load_cfn_template_success(self, tmp_path, monkeypatch):
        """Test successful CloudFormation template loading."""
        template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Resources:
  MyFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: app.lambda_handler
      Runtime: python3.9
"""
        template_file = tmp_path / "template.yaml"
        template_file.write_text(template_content)

        executor = Executor(working_dir=tmp_path)

        # Mock load_yaml to return parsed dict
        def mock_load_yaml(content):
            return {
                "AWSTemplateFormatVersion": "2010-09-09",
                "Transform": "AWS::Serverless-2016-10-31",
                "Resources": {"MyFunction": {"Type": "AWS::Serverless::Function", "Properties": {"Handler": "app.lambda_handler", "Runtime": "python3.9"}}},
            }

        monkeypatch.setattr("plldb.util.cfn.load_yaml", mock_load_yaml)

        result = executor.load_cfn_template()
        assert "Resources" in result
        assert "MyFunction" in result["Resources"]

    def test_load_cfn_template_file_not_found(self, tmp_path):
        """Test load_cfn_template when template file doesn't exist."""
        executor = Executor(working_dir=tmp_path, cfn_template_path=tmp_path / "nonexistent.yaml")

        with pytest.raises(FileNotFoundError):
            executor.load_cfn_template()


class TestWithEnvironment:
    """Test cases for with_environment context manager."""

    def test_with_environment_no_env(self):
        """Test with_environment with no environment variables."""
        executor = Executor()

        original_env = os.environ.copy()

        with executor.with_environment(None):
            # Environment should remain unchanged
            assert os.environ == original_env

        # Environment should be restored
        assert os.environ == original_env

    def test_with_environment_empty_dict(self):
        """Test with_environment with empty dictionary."""
        executor = Executor()

        original_env = os.environ.copy()

        with executor.with_environment({}):
            # Environment should remain unchanged
            assert os.environ == original_env

        # Environment should be restored
        assert os.environ == original_env

    def test_with_environment_new_vars(self):
        """Test with_environment with new environment variables."""
        executor = Executor()

        original_env = os.environ.copy()
        test_env = {"TEST_VAR_1": "value1", "TEST_VAR_2": "value2"}

        with executor.with_environment(test_env):
            # New variables should be set
            assert os.environ["TEST_VAR_1"] == "value1"
            assert os.environ["TEST_VAR_2"] == "value2"

        # Environment should be restored
        assert os.environ == original_env
        assert "TEST_VAR_1" not in os.environ
        assert "TEST_VAR_2" not in os.environ

    def test_with_environment_override_existing(self):
        """Test with_environment overriding existing variables."""
        executor = Executor()

        # Set an existing variable
        os.environ["EXISTING_VAR"] = "original_value"
        original_env = os.environ.copy()

        test_env = {"EXISTING_VAR": "new_value", "NEW_VAR": "new_var_value"}

        with executor.with_environment(test_env):
            # Variables should be updated
            assert os.environ["EXISTING_VAR"] == "new_value"
            assert os.environ["NEW_VAR"] == "new_var_value"

        # Environment should be restored
        assert os.environ == original_env
        assert os.environ["EXISTING_VAR"] == "original_value"
        assert "NEW_VAR" not in os.environ

    def test_with_environment_exception_handling(self):
        """Test with_environment properly restores state on exception."""
        executor = Executor()

        original_env = os.environ.copy()
        test_env = {"TEST_VAR": "test_value"}

        with pytest.raises(RuntimeError):
            with executor.with_environment(test_env):
                assert os.environ["TEST_VAR"] == "test_value"
                raise RuntimeError("Test exception")

        # Environment should be restored despite exception
        assert os.environ == original_env
        assert "TEST_VAR" not in os.environ


class TestInvokeLambdaFunction:
    """Test cases for invoke_lambda_function method."""

    @pytest.fixture
    def mock_lambda_setup(self, tmp_path, monkeypatch):
        """Set up mock lambda function for testing."""
        # Create lambda code
        lambda_dir = tmp_path / "lambda_code"
        lambda_dir.mkdir()

        app_py = lambda_dir / "app.py"
        app_py.write_text("""
import os

def lambda_handler(event, context):
    # Check for environment variables
    env_var = os.environ.get("TEST_ENV_VAR", "default")
    
    return {
        "statusCode": 200,
        "body": f"Event: {event}, Env: {env_var}",
        "requestId": context.aws_request_id,
        "functionName": context.function_name
    }

def error_handler(event, context):
    raise ValueError("Test error from lambda")
""")

        # Create CloudFormation template
        template = {
            "Resources": {
                "TestLambda": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "lambda_code", "Handler": "app.lambda_handler"}},
                "ErrorLambda": {"Type": "AWS::Serverless::Function", "Properties": {"CodeUri": "lambda_code", "Handler": "app.error_handler"}},
            }
        }

        return tmp_path, template

    def test_invoke_lambda_function_basic(self, mock_lambda_setup, monkeypatch):
        """Test basic lambda function invocation."""
        working_dir, template = mock_lambda_setup

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: template)

        event = {"test": "data"}
        result = executor.invoke_lambda_function("TestLambda", event)

        assert result["statusCode"] == 200
        assert "Event: {'test': 'data'}" in result["body"]
        assert "requestId" in result
        assert result["functionName"] == "TestLambda"

    def test_invoke_lambda_function_with_context(self, mock_lambda_setup, monkeypatch):
        """Test lambda function invocation with custom context."""
        working_dir, template = mock_lambda_setup

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: template)

        # Create custom context
        custom_context = type(
            "CustomContext",
            (),
            {
                "aws_request_id": "custom-request-id",
                "function_name": "CustomFunctionName",
                "function_version": "2",
                "invoked_function_arn": "arn:aws:lambda:custom",
                "memory_limit_in_mb": 256,
                "remaining_time_in_millis": lambda: 600000,
            },
        )()

        event = {"test": "data"}
        result = executor.invoke_lambda_function("TestLambda", event, custom_context)

        assert result["requestId"] == "custom-request-id"
        assert result["functionName"] == "CustomFunctionName"

    def test_invoke_lambda_function_with_environment(self, mock_lambda_setup, monkeypatch):
        """Test lambda function invocation with environment variables."""
        working_dir, template = mock_lambda_setup

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: template)

        event = {"test": "data"}
        environment = {"TEST_ENV_VAR": "custom_value"}

        result = executor.invoke_lambda_function("TestLambda", event, environment=environment)

        assert "Env: custom_value" in result["body"]

    def test_invoke_lambda_function_default_context(self, mock_lambda_setup, monkeypatch):
        """Test lambda function invocation with default context."""
        working_dir, template = mock_lambda_setup

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: template)

        event = {"test": "data"}
        result = executor.invoke_lambda_function("TestLambda", event)

        # Check default context properties
        assert "requestId" in result
        assert result["functionName"] == "TestLambda"

        # Request ID should be a valid UUID format
        import uuid

        try:
            uuid.UUID(result["requestId"])
        except ValueError:
            pytest.fail("Request ID is not a valid UUID")

    def test_invoke_lambda_function_error_propagation(self, mock_lambda_setup, monkeypatch):
        """Test that lambda function errors are propagated correctly."""
        working_dir, template = mock_lambda_setup

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: template)

        with pytest.raises(ValueError) as exc_info:
            executor.invoke_lambda_function("ErrorLambda", {})

        assert "Test error from lambda" in str(exc_info.value)

    def test_invoke_lambda_function_not_found(self, mock_lambda_setup, monkeypatch):
        """Test invoke_lambda_function with non-existent function."""
        working_dir, template = mock_lambda_setup

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: template)

        with pytest.raises(LambdaFunctionNotFoundError):
            executor.invoke_lambda_function("NonExistentLambda", {})

    def test_invoke_lambda_function_complex_event(self, mock_lambda_setup, monkeypatch):
        """Test lambda function invocation with complex event data."""
        working_dir, template = mock_lambda_setup

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: template)

        complex_event = {
            "Records": [{"eventSource": "aws:s3", "s3": {"bucket": {"name": "test-bucket"}, "object": {"key": "test-object.txt"}}}],
            "metadata": {"timestamp": "2024-01-01T00:00:00Z", "source": "test"},
        }

        result = executor.invoke_lambda_function("TestLambda", complex_event)

        assert result["statusCode"] == 200
        assert "Records" in result["body"]

    def test_invoke_lambda_function_environment_isolation(self, mock_lambda_setup, monkeypatch):
        """Test that environment changes don't leak between invocations."""
        working_dir, template = mock_lambda_setup

        executor = Executor(working_dir=working_dir)
        monkeypatch.setattr(executor, "load_cfn_template", lambda: template)

        # First invocation with environment
        env1 = {"TEST_ENV_VAR": "first_value"}
        result1 = executor.invoke_lambda_function("TestLambda", {}, environment=env1)
        assert "Env: first_value" in result1["body"]

        # Second invocation without environment
        result2 = executor.invoke_lambda_function("TestLambda", {})
        assert "Env: default" in result2["body"]

        # Third invocation with different environment
        env3 = {"TEST_ENV_VAR": "third_value"}
        result3 = executor.invoke_lambda_function("TestLambda", {}, environment=env3)
        assert "Env: third_value" in result3["body"]


class TestExecutorSimulator:
    def test_with_real_filesystem(self, tmp_path):
        """
        Create tempdir
        Similate virtual environment .venv
        Put example site package there, for example
          .venv/lib/python3.13/site-packages/foo
          .venv/lib/python3.13/site-packages/foo/__init__.py
          .venv/lib/python3.13/site-packages/foo/bar.py
        Create baz function in the foo.bar module

        Create a lambda function in the tempdir
        Put a lambda function handler there, for example
            return foo.bar.baz()

        Create a CloudFormation template with a lambda function that uses the foo.bar.baz function
        Run the test for Executor in that dir
        """
        # Create virtual environment structure
        venv_path = tmp_path / ".venv"

        # Determine Python version for site-packages path
        python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"

        if sys.platform == "win32":
            site_packages = venv_path / "Lib" / "site-packages"
        else:
            site_packages = venv_path / "lib" / python_version / "site-packages"

        site_packages.mkdir(parents=True)

        # Create custom package 'foo' in site-packages
        foo_package = site_packages / "foo"
        foo_package.mkdir()

        # Create __init__.py for foo package
        (foo_package / "__init__.py").write_text('"""Foo package for testing."""\n')

        # Create bar.py module with baz function
        bar_module = foo_package / "bar.py"
        bar_module.write_text("""
def baz():
    \"\"\"Test function that returns a specific value.\"\"\"
    return {"message": "Hello from foo.bar.baz!", "status": "success"}
""")

        # Create lambda code directory
        lambda_code_dir = tmp_path / "lambda_code"
        lambda_code_dir.mkdir()

        # Create Lambda handler that uses foo.bar.baz
        lambda_handler = lambda_code_dir / "handler.py"
        lambda_handler.write_text("""
import json
import foo.bar

def lambda_handler(event, context):
    \"\"\"Lambda handler that uses the foo.bar.baz function.\"\"\"
    # Call the function from our custom package
    result = foo.bar.baz()
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "event": event,
            "result": result,
            "context": {
                "function_name": context.function_name,
                "request_id": context.aws_request_id
            }
        })
    }
""")

        # Create CloudFormation template
        cfn_template = tmp_path / "template.yaml"
        cfn_template.write_text("""
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  TestFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: lambda_code
      Handler: handler.lambda_handler
      Runtime: python3.9
      MemorySize: 128
      Timeout: 30
""")

        # Create Executor instance
        executor = Executor(working_dir=tmp_path, cfn_template_path=cfn_template)

        # Test invoke_lambda_function with custom package
        event = {"testKey": "testValue", "action": "test"}

        # This should:
        # 1. Load site-packages from .venv
        # 2. Import the lambda handler
        # 3. Execute it with access to foo.bar.baz
        result = executor.invoke_lambda_function("TestFunction", event)

        # Verify the result
        assert result["statusCode"] == 200

        # Parse the body
        import json

        body = json.loads(result["body"])

        # Check that the event was passed correctly
        assert body["event"] == event

        # Check that foo.bar.baz was called successfully
        assert body["result"]["message"] == "Hello from foo.bar.baz!"
        assert body["result"]["status"] == "success"

        # Check context was set
        assert body["context"]["function_name"] == "TestFunction"
        assert "request_id" in body["context"]

        # Test with environment variables
        env_vars = {"CUSTOM_ENV": "test_value", "LOG_LEVEL": "DEBUG"}

        # Create another lambda that uses environment variables
        env_handler = lambda_code_dir / "env_handler.py"
        env_handler.write_text("""
import os
import json
import foo.bar

def env_lambda_handler(event, context):
    \"\"\"Lambda handler that uses environment variables and foo.bar.\"\"\"
    result = foo.bar.baz()
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "foo_result": result,
            "env": {
                "CUSTOM_ENV": os.environ.get("CUSTOM_ENV", "not_set"),
                "LOG_LEVEL": os.environ.get("LOG_LEVEL", "not_set")
            }
        })
    }
""")

        # Update template to include the new function
        updated_template = (
            cfn_template.read_text()
            + """
  EnvTestFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: lambda_code
      Handler: env_handler.env_lambda_handler
      Runtime: python3.9
"""
        )
        cfn_template.write_text(updated_template)

        # Test with environment variables
        result = executor.invoke_lambda_function("EnvTestFunction", {"test": "env"}, environment=env_vars)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])

        # Verify environment variables were set
        assert body["env"]["CUSTOM_ENV"] == "test_value"
        assert body["env"]["LOG_LEVEL"] == "DEBUG"

        # Verify foo.bar.baz still works
        assert body["foo_result"]["message"] == "Hello from foo.bar.baz!"

        # Test that the module is cleaned up after execution
        assert "handler" not in sys.modules
        assert "env_handler" not in sys.modules

        # Test error handling when function doesn't exist
        with pytest.raises(LambdaFunctionNotFoundError):
            executor.invoke_lambda_function("NonExistentFunction", {})
