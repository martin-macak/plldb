"""Protocol dataclasses for PLLDB debugger communication."""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class DebuggerRequest:
    """WebSocket request from Lambda runtime to debugger."""

    requestId: str
    sessionId: str
    connectionId: str
    lambdaFunctionName: str
    lambdaFunctionVersion: str
    event: str
    environmentVariables: Optional[Dict[str, str]] = None


@dataclass
class DebuggerResponse:
    """WebSocket response from debugger to Lambda runtime."""

    requestId: str
    statusCode: int
    response: str
    errorMessage: Optional[str] = None


@dataclass
class DebuggerInfo:
    """WebSocket info/log message from backend Lambda to debugger."""

    sessionId: str
    connectionId: str
    logLevel: str
    message: str
    timestamp: str
