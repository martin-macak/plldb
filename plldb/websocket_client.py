import asyncio
import dataclasses
import json
import logging
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional, Union
from urllib.parse import urlparse, urlunparse

import websockets

from plldb.debugger import InvalidMessageError
from plldb.protocol import DebuggerRequest, DebuggerResponse, DebuggerInfo

logger = logging.getLogger(__name__)


class WebSocketClient:
    """WebSocket client for debugging sessions."""

    def __init__(self, websocket_url: str, session_id: str):
        """Initialize WebSocket client.

        Args:
            websocket_url: Base WebSocket URL (without query params)
            session_id: Session ID for authentication
        """
        # Parse URL and add sessionId query parameter
        parsed = urlparse(websocket_url)
        query = f"sessionId={session_id}"
        self.url = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                query,
                parsed.fragment,
            )
        )
        self.session_id = session_id
        self._running = False
        self._websocket: Optional[Any] = None  # WebSocket connection
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def connect(self) -> None:
        """Connect to the WebSocket API."""
        logger.info(f"Connecting to WebSocket: {self.url}")
        self._websocket = await websockets.connect(self.url)
        logger.info("WebSocket connection established")

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket API."""
        if self._websocket:
            await self._websocket.close()
            self._websocket = None
            logger.info("WebSocket connection closed")

    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send a message to the WebSocket.

        Args:
            message: Dictionary to send as JSON
        """
        if not self._websocket:
            raise RuntimeError("WebSocket not connected")

        logger.debug(f"Sending WebSocket message: {message}")
        await self._websocket.send(json.dumps(message))
        logger.debug(f"Sent WebSocket message: {message}")

    async def receive_message(self) -> Dict[str, Any]:
        """Receive a message from the WebSocket.

        Returns:
            Parsed JSON message

        Raises:
            RuntimeError: If WebSocket not connected
            websockets.exceptions.ConnectionClosed: If connection closed
        """
        if not self._websocket:
            raise RuntimeError("WebSocket not connected")

        raw_message = await self._websocket.recv()
        logger.debug(f"Received WebSocket message: {raw_message}")
        return json.loads(raw_message)

    async def run_loop(
        self,
        message_handler: Optional[Callable[[Dict[str, Any]], Union[DebuggerResponse, None]]] = None,
    ) -> None:
        """Run the main message loop.

        Args:
            message_handler: Optional callback for handling messages
        """
        self._running = True

        # Set up signal handlers
        loop = asyncio.get_event_loop()

        def signal_handler():
            logger.info("Received interrupt signal, shutting down...")
            self._running = False

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        try:
            await self.connect()

            while self._running:
                try:
                    message = await asyncio.wait_for(self.receive_message(), timeout=1.0)
                    logger.info(f"Received message: {message}")

                    if message_handler:
                        # Check if this is a DebuggerInfo message
                        if "logLevel" in message and "timestamp" in message:
                            # Handle DebuggerInfo messages
                            try:
                                info = DebuggerInfo(**message)
                            except (TypeError, KeyError) as e:
                                logger.error(f"Failed to deserialize DebuggerInfo message: {e}")
                                continue
                        else:
                            # Deserialize message to DebuggerRequest
                            try:
                                request = DebuggerRequest(**message)
                            except (TypeError, KeyError) as e:
                                logger.error(f"Failed to deserialize DebuggerRequest message: {e}")
                                continue

                        # Run handler in a separate thread
                        future = loop.run_in_executor(self._executor, message_handler, message)
                        logger.debug(f"Received result from message handler")

                        try:
                            result = await future

                            if isinstance(result, DebuggerResponse):
                                # Send WebSocket message with result
                                logger.debug(f"Got DebuggerResponse from message handler {result}")
                                await self.send_message(dataclasses.asdict(result))
                            # If result is None (from DebuggerInfo), don't send response
                        except InvalidMessageError as e:
                            logger.error(f"Invalid message: {e}")
                            sys.exit(1)
                        except Exception as e:
                            logger.error(f"Error in message handler: {e}")
                            # Only send error response for DebuggerRequest messages
                            if "requestId" in message:
                                error_response = DebuggerResponse(
                                    requestId=message["requestId"],
                                    statusCode=500,
                                    response="",
                                    errorMessage=str(e),
                                )
                                await self.send_message(dataclasses.asdict(error_response))
                            continue

                except asyncio.TimeoutError:
                    # Timeout is normal, just continue the loop
                    continue
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("WebSocket connection closed by server")
                    break
                except Exception as e:
                    logger.error(f"Error in message loop: {e}")
                    break

        finally:
            # Clean up signal handlers
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.remove_signal_handler(sig)

            await self.disconnect()
            self._executor.shutdown(wait=True)

    def stop(self) -> None:
        """Stop the message loop."""
        self._running = False
