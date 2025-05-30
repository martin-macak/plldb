# REQ-FN-0011 - debugpy support

Debugpy server is started when the `plldb attach` command is run.

## Requirements

- Debugpy server is started when the `plldb attach` command is run.
- New optional argument `--debugpy` is added to the `plldb attach` command to enable debugpy server. This is default by false.
- New optional argument `--debugpy-port` is added to the `plldb attach` command to specify the port for the debugpy server. This is default by 5678.
- New optional argument `--debugpy-host` is added to the `plldb attach` command to specify the host for the debugpy server. This is default by 127.0.0.1.

## Help message

When the debugpy server is enabled, print the following help message:

```
Debugpy server is enabled and it runs on <host>:<port>.
To attach to the debugpy server from the visual studio code, you can use the following launch configuration:

{
    "name": "Python Debugger: Remote Attach",
    "type": "debugpy",
    "request": "attach",
    "connect": { "host": "<host>", "port": <port> }
}

If you don't have your debug configurations yet, create `.vscode/launch.json` file with the following content:

{
    "configurations": [
        "name": "Python Debugger: Remote Attach",
        "type": "debugpy",
        "request": "attach",
        "connect": { "host": "<host>", "port": <port> }
    ]
}
```

## Debugpy server is started when the `plldb attach` command is run.