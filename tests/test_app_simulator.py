import subprocess
import sys

import pytest


@pytest.mark.cli
class TestSimulatorCLI:
    """Test simulator CLI functionality."""

    def test_simulator_simple_invocation(self):
        """Test simple function invocation through CLI."""
        # Run simulator with a simple invoke command
        process = subprocess.Popen(
            [sys.executable, "-m", "plldb", "simulator", "start", "-d", "test_stack"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send invoke command and exit
        stdout, stderr = process.communicate(input='invoke TestFunction {"name": "World"}\nexit\n')

        # Check output
        assert process.returncode == 0
        assert "Simulator started" in stdout
        assert "Result:" in stdout
        assert '"statusCode": 200' in stdout
        assert '"body": "Hello, World!"' in stdout
        assert "Exiting simulator" in stdout

    def test_simulator_with_environment_variables(self):
        """Test function invocation with environment variables through CLI."""
        # Run simulator with environment variables
        process = subprocess.Popen(
            [sys.executable, "-m", "plldb", "simulator", "start", "-d", "test_stack"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send invoke command with env vars and exit
        stdout, stderr = process.communicate(input='invoke TestFunction --env GREETING=Hi --env NAME=Claude {"name": "Test"}\nexit\n')

        # Check output
        assert process.returncode == 0
        assert "Simulator started" in stdout
        assert "Result:" in stdout
        assert '"statusCode": 200' in stdout
        assert "Exiting simulator" in stdout

    def test_simulator_invalid_command(self):
        """Test handling of invalid commands through CLI."""
        # Run simulator with invalid command
        process = subprocess.Popen(
            [sys.executable, "-m", "plldb", "simulator", "start", "-d", "test_stack"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send invalid command and exit
        stdout, stderr = process.communicate(input="invalid command\nexit\n")

        # Check output
        assert process.returncode == 0
        assert "Simulator started" in stdout
        assert "Error: Unknown command: invalid" in stdout
        assert "Exiting simulator" in stdout

    def test_simulator_keyboard_interrupt(self):
        """Test handling of keyboard interrupt through CLI."""
        # Run simulator
        process = subprocess.Popen(
            [sys.executable, "-m", "plldb", "simulator", "start", "-d", "test_stack"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send empty input to trigger EOF
        stdout, stderr = process.communicate(input="")

        # Check output
        assert process.returncode == 0
        assert "Simulator started" in stdout
        assert "Exiting simulator" in stdout

    def test_simulator_missing_template(self, tmp_path):
        """Test error when template is not found."""
        # Run simulator with non-existent directory
        process = subprocess.Popen(
            [sys.executable, "-m", "plldb", "simulator", "start", "-d", str(tmp_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stdout, stderr = process.communicate()

        # Check output
        assert process.returncode == 1
        assert "Template not found" in stderr

    @pytest.mark.parametrize(
        "command,expected_in_output",
        [
            ('invoke TestFunction {"empty": true}', '"statusCode": 200'),
            ('invoke TestFunction {"name": "Test"}', '"body": "Hello, World!"'),
            ("invoke NonExistent {}", "Lambda function 'NonExistent' not found"),
            ("invoke TestFunction invalid-json", "Invalid event JSON"),
            ("invoke", "Invalid invoke command: missing required arguments"),
        ],
    )
    def test_simulator_various_commands(self, command, expected_in_output):
        """Test various simulator commands through CLI."""
        # Run simulator
        process = subprocess.Popen(
            [sys.executable, "-m", "plldb", "simulator", "start", "-d", "test_stack"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send command and exit
        stdout, stderr = process.communicate(input=f"{command}\nexit\n")

        # Check output
        assert process.returncode == 0
        assert expected_in_output in stdout
