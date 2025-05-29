import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
import yaml

from plldb.executor import Executor


class ParseError(Exception):
    """Raised when command parsing fails."""

    pass


class Parser:
    """Parses simulator commands."""

    def parse_invoke(self, command: str) -> Tuple[str, Dict[str, str], str]:
        """Parse invoke command.

        Args:
            command: The command string to parse

        Returns:
            Tuple of (logical_id, environment_variables, event)

        Raises:
            ParseError: If command is invalid
        """
        # Remove extra spaces and split by whitespace
        parts = command.strip().split()

        if len(parts) < 2 or parts[0] != "invoke":
            raise ParseError("Invalid invoke command: missing required arguments")

        if len(parts) < 3:
            raise ParseError("Invalid invoke command: missing event argument")

        logical_id = parts[1]
        env_vars = {}
        event_index = 2

        # Parse environment variables
        i = 2
        while i < len(parts):
            if parts[i] == "--env":
                if i + 1 >= len(parts):
                    raise ParseError("Invalid invoke command: --env requires a value")
                env_pair = parts[i + 1]
                if "=" not in env_pair:
                    raise ParseError(f"Invalid environment variable format: {env_pair}")
                key, value = env_pair.split("=", 1)
                env_vars[key] = value
                i += 2
                event_index = i
            else:
                break

        # Get the event (rest of the command)
        if event_index >= len(parts):
            raise ParseError("Invalid invoke command: missing event argument")

        # Join the rest as the event JSON
        event = " ".join(parts[event_index:])

        # Validate event is valid JSON
        try:
            json.loads(event)
        except json.JSONDecodeError as e:
            raise ParseError(f"Invalid event JSON: {e}")

        return logical_id, env_vars, event

    def parse_exit(self, command: str) -> bool:
        """Parse exit command.

        Args:
            command: The command string to parse

        Returns:
            True if valid exit command

        Raises:
            ParseError: If command is invalid
        """
        if command.strip() != "exit":
            raise ParseError("Invalid exit command")
        return True

    def parse(self, command: str) -> Dict[str, Any]:
        """Parse a command.

        Args:
            command: The command string to parse

        Returns:
            Dictionary with parsed command information

        Raises:
            ParseError: If command is invalid
        """
        command = command.strip()
        if not command:
            raise ParseError("Empty command")

        if command.startswith("invoke"):
            logical_id, env_vars, event = self.parse_invoke(command)
            return {
                "type": "invoke",
                "logical_id": logical_id,
                "env_vars": env_vars,
                "event": event,
            }
        elif command == "exit":
            return {"type": "exit"}
        else:
            raise ParseError(f"Unknown command: {command.split()[0]}")


class Simulator:
    """Local Lambda function simulator."""

    def __init__(self, template_path: Path, working_directory: Path):
        """Initialize simulator.

        Args:
            template_path: Path to CloudFormation template
            working_directory: Working directory for the simulator
        """
        self.template_path = template_path
        self.working_directory = working_directory
        self.parser = Parser()
        self.executor = None
        self.template = None

    def load_template(self) -> None:
        """Load CloudFormation template."""
        with open(self.template_path, "r") as f:
            self.template = yaml.safe_load(f)

    def find_lambda_function(self, logical_id: str) -> Dict[str, Any]:
        """Find Lambda function in template by logical ID.

        Args:
            logical_id: Logical ID of the Lambda function

        Returns:
            Lambda function resource definition

        Raises:
            ValueError: If function not found
        """
        if not self.template:
            raise ValueError("Template not loaded")

        resources = self.template.get("Resources", {})
        resource = resources.get(logical_id)

        if not resource:
            raise ValueError(f"Lambda function with logical ID '{logical_id}' not found")

        if resource.get("Type") != "AWS::Serverless::Function":
            raise ValueError(f"Resource '{logical_id}' is not a Lambda function")

        return resource

    def invoke_function(self, logical_id: str, event: str, env_vars: Dict[str, str]) -> Any:
        """Invoke a Lambda function.

        Args:
            logical_id: Logical ID of the Lambda function
            event: Event JSON string
            env_vars: Environment variables

        Returns:
            Function execution result
        """
        # Parse event
        event_data = json.loads(event)

        # Create executor for this invocation
        executor = Executor(working_dir=self.working_directory, cfn_template_path=self.template_path)

        # Execute function with environment variables
        result = executor.invoke_lambda_function(lambda_function_logical_id=logical_id, event=event_data, environment=env_vars)

        return result

    def run(self) -> None:
        """Run the simulator read-eval loop."""
        self.load_template()
        print(f"Simulator started. Template: {self.template_path}")
        print("Type 'exit' to quit.")
        print()

        while True:
            try:
                # Read command
                command = input("> ")

                # Parse command
                try:
                    parsed = self.parser.parse(command)
                except ParseError as e:
                    print(f"Error: {e}")
                    continue

                # Execute command
                if parsed["type"] == "exit":
                    print("Exiting simulator.")
                    break
                elif parsed["type"] == "invoke":
                    try:
                        result = self.invoke_function(parsed["logical_id"], parsed["event"], parsed["env_vars"])
                        print(f"Result: {json.dumps(result, indent=2)}")
                    except Exception as e:
                        print(f"Error: {e}")

            except KeyboardInterrupt:
                print("\nExiting simulator.")
                break
            except EOFError:
                print("\nExiting simulator.")
                break


def start_simulator(template: Optional[str] = None, directory: Optional[str] = None) -> None:
    """Start the simulator.

    Args:
        template: Path to CloudFormation template
        directory: Working directory for simulator
    """
    # Resolve paths
    if template and os.path.isabs(template):
        # Absolute template path
        template_path = Path(template)
        if directory:
            raise ValueError("Cannot specify both absolute template path and directory")
        working_directory = template_path.parent
    else:
        # Relative template or default
        if directory:
            working_directory = Path(directory).resolve()
        else:
            working_directory = Path.cwd()

        if template:
            template_path = working_directory / template
        else:
            template_path = working_directory / "template.yaml"

    # Validate template exists
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    # Create and run simulator
    simulator = Simulator(template_path, working_directory)
    simulator.run()
