import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from plldb.simulator import ParseError, Parser, Simulator, start_simulator


class TestParser:
    """Test Parser class."""

    @pytest.fixture
    def parser(self):
        """Create a Parser instance."""
        return Parser()

    @pytest.mark.parametrize(
        "command,expected_error",
        [
            ("invoke", "Invalid invoke command: missing required arguments"),
            ("invoke test_fn_1", "Invalid invoke command: missing event argument"),
            (
                "invoke test_fn_1 --env",
                "Invalid invoke command: --env requires a value",
            ),
            (
                "invoke test_fn_1 --env invalid_format {}",
                "Invalid environment variable format: invalid_format",
            ),
            (
                "invoke test_fn_1 {invalid json}",
                "Invalid event JSON:",
            ),
        ],
    )
    def test_parse_invoke_invalid(self, parser, command, expected_error):
        """Test invalid invoke commands."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse_invoke(command)
        assert expected_error in str(exc_info.value)

    @pytest.mark.parametrize(
        "command,expected_logical_id,expected_env_vars,expected_event",
        [
            (
                'invoke test_fn_1 --env env1=value1 --env env2=value2 {"key": "value"}',
                "test_fn_1",
                {"env1": "value1", "env2": "value2"},
                '{"key": "value"}',
            ),
            (
                'invoke   test_fn_1  --env env1=value1 --env env2=value2 {"key": "value"}',
                "test_fn_1",
                {"env1": "value1", "env2": "value2"},
                '{"key": "value"}',
            ),
            (
                'invoke test_fn_1 {"key": "value"}',
                "test_fn_1",
                {},
                '{"key": "value"}',
            ),
            (
                "invoke test_fn_1 {}",
                "test_fn_1",
                {},
                "{}",
            ),
            (
                'invoke test_fn_1 --env FOO=bar {"nested": {"key": "value"}}',
                "test_fn_1",
                {"FOO": "bar"},
                '{"nested": {"key": "value"}}',
            ),
        ],
    )
    def test_parse_invoke_valid(self, parser, command, expected_logical_id, expected_env_vars, expected_event):
        """Test valid invoke commands."""
        logical_id, env_vars, event = parser.parse_invoke(command)
        assert logical_id == expected_logical_id
        assert env_vars == expected_env_vars
        assert json.loads(event) == json.loads(expected_event)

    @pytest.mark.parametrize(
        "command,expected_valid",
        [
            ("exit", True),
            ("exit    ", True),
            ("   exit", True),
            ("   exit   ", True),
        ],
    )
    def test_parse_exit_valid(self, parser, command, expected_valid):
        """Test valid exit commands."""
        result = parser.parse_exit(command)
        assert result == expected_valid

    @pytest.mark.parametrize(
        "command",
        [
            "exit something",
            "exits",
            "exi",
            "exit --help",
        ],
    )
    def test_parse_exit_invalid(self, parser, command):
        """Test invalid exit commands."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse_exit(command)
        assert "Invalid exit command" in str(exc_info.value)

    def test_parse_empty_command(self, parser):
        """Test parsing empty command."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse("")
        assert "Empty command" in str(exc_info.value)

    def test_parse_unknown_command(self, parser):
        """Test parsing unknown command."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse("unknown command")
        assert "Unknown command: unknown" in str(exc_info.value)

    def test_parse_invoke_command(self, parser):
        """Test parsing invoke command through main parse method."""
        result = parser.parse('invoke test_fn_1 {"key": "value"}')
        assert result == {
            "type": "invoke",
            "logical_id": "test_fn_1",
            "env_vars": {},
            "event": '{"key": "value"}',
        }

    def test_parse_exit_command(self, parser):
        """Test parsing exit command through main parse method."""
        result = parser.parse("exit")
        assert result == {"type": "exit"}


class TestSimulator:
    """Test Simulator class."""

    @pytest.fixture
    def template_content(self):
        """Sample CloudFormation template."""
        return {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Resources": {
                "TestFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "Handler": "app.lambda_handler",
                        "Runtime": "python3.9",
                        "CodeUri": "./test_fn_1",
                    },
                },
                "NotALambda": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {"BucketName": "test-bucket"},
                },
            },
        }

    @pytest.fixture
    def simulator(self, tmp_path, template_content):
        """Create a Simulator instance with a test template."""
        template_path = tmp_path / "template.yaml"
        with open(template_path, "w") as f:
            yaml.dump(template_content, f)

        return Simulator(template_path, tmp_path)

    def test_load_template(self, simulator):
        """Test loading CloudFormation template."""
        simulator.load_template()
        assert simulator.template is not None
        assert "Resources" in simulator.template

    def test_find_lambda_function(self, simulator):
        """Test finding Lambda function by logical ID."""
        simulator.load_template()
        function = simulator.find_lambda_function("TestFunction")
        assert function["Type"] == "AWS::Serverless::Function"
        assert function["Properties"]["Handler"] == "app.lambda_handler"

    def test_find_lambda_function_not_found(self, simulator):
        """Test finding non-existent Lambda function."""
        simulator.load_template()
        with pytest.raises(ValueError) as exc_info:
            simulator.find_lambda_function("NonExistent")
        assert "Lambda function with logical ID 'NonExistent' not found" in str(exc_info.value)

    def test_find_lambda_function_not_lambda(self, simulator):
        """Test finding resource that is not a Lambda function."""
        simulator.load_template()
        with pytest.raises(ValueError) as exc_info:
            simulator.find_lambda_function("NotALambda")
        assert "Resource 'NotALambda' is not a Lambda function" in str(exc_info.value)

    def test_find_lambda_function_template_not_loaded(self, simulator):
        """Test finding Lambda function when template not loaded."""
        with pytest.raises(ValueError) as exc_info:
            simulator.find_lambda_function("TestFunction")
        assert "Template not loaded" in str(exc_info.value)

    @patch("plldb.simulator.Executor")
    def test_invoke_function(self, mock_executor_class, simulator, tmp_path):
        """Test invoking a Lambda function."""
        # Create test function code
        code_dir = tmp_path / "test_fn_1"
        code_dir.mkdir()
        with open(code_dir / "app.py", "w") as f:
            f.write("def lambda_handler(event, context):\n    return {'statusCode': 200}")

        # Setup mock executor
        mock_executor = MagicMock()
        mock_executor.invoke_lambda_function.return_value = {"statusCode": 200, "body": "Success"}
        mock_executor_class.return_value = mock_executor

        # Load template and invoke
        simulator.load_template()
        result = simulator.invoke_function("TestFunction", '{"key": "value"}', {"ENV_VAR": "test"})

        # Verify
        assert result == {"statusCode": 200, "body": "Success"}
        mock_executor.invoke_lambda_function.assert_called_once_with(lambda_function_logical_id="TestFunction", event={"key": "value"}, environment={"ENV_VAR": "test"})

    @patch("builtins.input")
    def test_run_exit_command(self, mock_input, simulator):
        """Test running simulator with exit command."""
        mock_input.return_value = "exit"

        with patch("builtins.print") as mock_print:
            simulator.run()

        # Verify exit message printed
        mock_print.assert_any_call("Exiting simulator.")

    @patch("builtins.input")
    def test_run_keyboard_interrupt(self, mock_input, simulator):
        """Test running simulator with keyboard interrupt."""
        mock_input.side_effect = KeyboardInterrupt()

        with patch("builtins.print") as mock_print:
            simulator.run()

        # Verify exit message printed
        mock_print.assert_any_call("\nExiting simulator.")

    @patch("builtins.input")
    def test_run_eof_error(self, mock_input, simulator):
        """Test running simulator with EOF error."""
        mock_input.side_effect = EOFError()

        with patch("builtins.print") as mock_print:
            simulator.run()

        # Verify exit message printed
        mock_print.assert_any_call("\nExiting simulator.")

    @patch("builtins.input")
    def test_run_parse_error(self, mock_input, simulator):
        """Test running simulator with parse error."""
        mock_input.side_effect = ["invalid command", "exit"]

        with patch("builtins.print") as mock_print:
            simulator.run()

        # Verify error message printed
        mock_print.assert_any_call("Error: Unknown command: invalid")


class TestStartSimulator:
    """Test start_simulator function."""

    def test_start_simulator_default(self, tmp_path, monkeypatch):
        """Test starting simulator with default settings."""
        monkeypatch.chdir(tmp_path)
        template_path = tmp_path / "template.yaml"
        with open(template_path, "w") as f:
            yaml.dump({"Resources": {}}, f)

        with patch("plldb.simulator.Simulator") as mock_simulator_class:
            mock_simulator = MagicMock()
            mock_simulator_class.return_value = mock_simulator

            start_simulator()

            mock_simulator_class.assert_called_once_with(template_path, tmp_path)
            mock_simulator.run.assert_called_once()

    def test_start_simulator_with_directory(self, tmp_path):
        """Test starting simulator with directory option."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        template_path = subdir / "template.yaml"
        with open(template_path, "w") as f:
            yaml.dump({"Resources": {}}, f)

        with patch("plldb.simulator.Simulator") as mock_simulator_class:
            mock_simulator = MagicMock()
            mock_simulator_class.return_value = mock_simulator

            start_simulator(directory=str(subdir))

            mock_simulator_class.assert_called_once_with(template_path, subdir)
            mock_simulator.run.assert_called_once()

    def test_start_simulator_with_relative_template(self, tmp_path, monkeypatch):
        """Test starting simulator with relative template path."""
        monkeypatch.chdir(tmp_path)
        template_path = tmp_path / "custom.yaml"
        with open(template_path, "w") as f:
            yaml.dump({"Resources": {}}, f)

        with patch("plldb.simulator.Simulator") as mock_simulator_class:
            mock_simulator = MagicMock()
            mock_simulator_class.return_value = mock_simulator

            start_simulator(template="custom.yaml")

            mock_simulator_class.assert_called_once_with(template_path, tmp_path)
            mock_simulator.run.assert_called_once()

    def test_start_simulator_with_absolute_template(self, tmp_path):
        """Test starting simulator with absolute template path."""
        template_path = tmp_path / "template.yaml"
        with open(template_path, "w") as f:
            yaml.dump({"Resources": {}}, f)

        with patch("plldb.simulator.Simulator") as mock_simulator_class:
            mock_simulator = MagicMock()
            mock_simulator_class.return_value = mock_simulator

            start_simulator(template=str(template_path))

            mock_simulator_class.assert_called_once_with(template_path, tmp_path)
            mock_simulator.run.assert_called_once()

    def test_start_simulator_absolute_template_with_directory_error(self, tmp_path):
        """Test error when absolute template and directory are both specified."""
        template_path = tmp_path / "template.yaml"
        with open(template_path, "w") as f:
            yaml.dump({"Resources": {}}, f)

        with pytest.raises(ValueError) as exc_info:
            start_simulator(template=str(template_path), directory="/some/dir")
        assert "Cannot specify both absolute template path and directory" in str(exc_info.value)

    def test_start_simulator_template_not_found(self, tmp_path):
        """Test error when template file not found."""
        with pytest.raises(FileNotFoundError) as exc_info:
            start_simulator(directory=str(tmp_path))
        assert "Template not found" in str(exc_info.value)
