import asyncio
import json
import logging
import signal
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse, urlunparse

import websockets

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
        self.url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))
        self.session_id = session_id
        self._running = False
        self._websocket: Optional[Any] = None  # WebSocket connection

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

        await self._websocket.send(json.dumps(message))

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
        return json.loads(raw_message)

    async def run_loop(self, message_handler: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
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
                        message_handler(message)

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

    def stop(self) -> None:
        """Stop the message loop."""
        self._running = False
