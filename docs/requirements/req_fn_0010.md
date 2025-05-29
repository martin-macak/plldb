# REQ-FN-0010 - Local debugger simulation

Allow to run local simulator to test the debugger stack.

This adds new command `plldb simulator start` to start the simulator. Simulator runs and waits for command line input that instructs it to run a specific function.

## Command line arguments

### Command Simulator Start

Command that manages the simulator.

#### Subcommand `start`

This is the default subcommand for the `simulator` command.
The simulator is started in `pwd` unless `-d` or `--directory` is provided.
The simulator can be also started with `-t` or `--template` to specify the template to use. If the template path is relative, it is resolved relative to the current working directory. If the template path is absolute, it is used as is and it also overrides the `-d` or `--directory` argument so the working directory is set to the directory of the template. Using both `-t` and `-d` with absolute template path is not allowed.

- `-t` or `--template` - the template to use for the simulator. If not provided, the template in the current working directory is used.
- `-d` or `--directory` - the directory to use for the simulator. If not provided, the current working directory is used.

For example:
- cwd is /workdir, no arguments are provided, the simulator is started in /workdir and it tries to resolve /workdir/template.yaml
- cwd is /workdir, -t /template.yaml is provided, the simulator is started in /workdir and it uses /template.yaml as template
- cwd is /workdir, -d /workdir/subdir is provided, the simulator is started in /workdir/subdir and it tries to resolve /workdir/subdir/template.yaml
- cwd is /workdir, -t /template.yaml -d /workdir/subdir is provided, the error is raised because both `-t` and `-d` are provided with absolute template path

The simulator starts read-eval loop and waits for input.
SIGINT (Ctrl+C) or SIGTERM (Ctrl+D) will stop the simulator.

## Commands 

Commands are sent to the simulator via stdin. 
Command is a new line terminated string.

### Command invoke

`invoke <LogicalId> [--env <Environment>] <Event>`

Invokes the function with the given event.

- `<LogicalId>` - the logical id of the function to invoke.
- `<Event>` - the event to invoke the function with.
- `--env` - the key=value pair of environment variable. can be used multiple times to set multiple environment variables.

Foe example

```
invoke test_fn_1 --env env1=value1 --env env2=value2 {"key": "value"}
```

This command loads the template and finds the lambda function with logical id `test_fn_1`. It then uses `plldb.executor` to import and execute the function with the given event. It sets the environment variables to the given values.

```
invoke test_fn_1 {"key": "value"}
```

This command is equivalent to the previous one but without the environment variables.

The result of the function execution is printed to stdout.

If no environment variables are provided, the function is invoked with empty environment variables.

### Command exit

`exit`

Exits the simulator.

## Implementation notes

- to import the function, we need to use `plldb.executor`
- implement new module `plldb.simulator` that will be used to start the simulator and handle the commands.
- implement new class `plldb.simulator.Simulator` that will be used to start the simulator and handle the commands.
- implement new class `plldb.simulator.Parser` that will be used to parse the commands.
- write parametrized tests for the Parser class that tests various commands.

### Test cases

#### Parser

`invoke` is illegal command, it misses required arguments.
`invoke test_fn_1` is illegal command, it misses required arguments.
`invoke test_fn_1 --env env1=value1 --env env2=value2 {"key": "value"}` is legal command, it sets the environment variables to the given values.
`invoke   test_fn_1  --env env1=value1 --env env2=value2 {"key": "value"}` is legal command, it sets the environment variables to the given values. it also ignores the extra spaces. multiple spaces are allowed.
`exit    ` is legal command, it exits the simulator.
`exit` is legal command, it exits the simulator.