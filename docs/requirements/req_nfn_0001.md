# REQ-NFN-0001: Lambda logging

- add LOG_LEVEL environment variable to the lambda functions
- default to INFO level
- use `logging` module to log messages
- configure logging level from the environment variable
- use `logging.getLogger(__name__)` to get the logger
- don't configure logging in the lambda handler, it will be configured by the runtime
- don't use `extra`, it won't be printed
- use string interpolation to log variables and parameters
- always use `f"Something happened {var=}` to print variable name and value
- use json.dumps to log dictionaries and lists. those can be logged only in DEBUG level

## Logging requirements

- event must be logged at DEBUG level
- return value must be logged at DEBUG level
- unauthorized access must be logged at INFO level
- session creation must be logged at INFO level
- session expiration must be logged at INFO level