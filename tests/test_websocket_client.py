import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
import websockets

from plldb.protocol import DebuggerResponse
from plldb.websocket_client import WebSocketClient


class TestWebSocketClient:
    def test_init(self):
        """Test WebSocket client initialization."""
        client = WebSocketClient("wss://example.com/ws", "test-session-id")
        assert client.url == "wss://example.com/ws?sessionId=test-session-id"
        assert client.session_id == "test-session-id"
        assert client._running is False
        assert client._websocket is None

    @pytest.mark.asyncio
    async def test_connect(self):
        """Test WebSocket connection."""
        mock_ws = AsyncMock()

        with patch("plldb.websocket_client.websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_ws

            client = WebSocketClient("wss://example.com/ws", "test-session-id")
            await client.connect()

            mock_connect.assert_called_once_with("wss://example.com/ws?sessionId=test-session-id")
            assert client._websocket == mock_ws

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test WebSocket disconnection."""
        client = WebSocketClient("wss://example.com/ws", "test-session-id")
        mock_ws = AsyncMock()
        client._websocket = mock_ws

        await client.disconnect()

        mock_ws.close.assert_called_once()
        assert client._websocket is None

    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test sending message."""
        client = WebSocketClient("wss://example.com/ws", "test-session-id")
        client._websocket = AsyncMock()

        message = {"action": "test", "data": "value"}
        await client.send_message(message)

        client._websocket.send.assert_called_once_with(json.dumps(message))

    @pytest.mark.asyncio
    async def test_send_message_not_connected(self):
        """Test error when sending without connection."""
        client = WebSocketClient("wss://example.com/ws", "test-session-id")

        with pytest.raises(RuntimeError, match="WebSocket not connected"):
            await client.send_message({"test": "data"})

    @pytest.mark.asyncio
    async def test_receive_message(self):
        """Test receiving message."""
        client = WebSocketClient("wss://example.com/ws", "test-session-id")
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = '{"action": "test", "data": "value"}'
        client._websocket = mock_ws

        message = await client.receive_message()

        assert message == {"action": "test", "data": "value"}
        mock_ws.recv.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_message_not_connected(self):
        """Test error when receiving without connection."""
        client = WebSocketClient("wss://example.com/ws", "test-session-id")

        with pytest.raises(RuntimeError, match="WebSocket not connected"):
            await client.receive_message()

    @pytest.mark.asyncio
    async def test_run_loop_with_messages(self):
        """Test message loop with handler."""
        # Mock WebSocket
        mock_ws = AsyncMock()
        messages = [
            json.dumps(
                {"requestId": "req-1", "sessionId": "test-session-id", "connectionId": "conn-1", "lambdaFunctionName": "test-function", "lambdaFunctionVersion": "$LATEST", "event": "test-event-1"}
            ),
            json.dumps(
                {"requestId": "req-2", "sessionId": "test-session-id", "connectionId": "conn-1", "lambdaFunctionName": "test-function", "lambdaFunctionVersion": "$LATEST", "event": "test-event-2"}
            ),
        ]
        mock_ws.recv.side_effect = messages + [websockets.exceptions.ConnectionClosed(None, None)]

        # Mock message handler that returns DebuggerResponse
        handler = Mock()
        handler.side_effect = [DebuggerResponse(requestId="req-1", statusCode=200, response="response-1"), DebuggerResponse(requestId="req-2", statusCode=200, response="response-2")]

        # Create client and run loop
        client = WebSocketClient("wss://example.com/ws", "test-session-id")

        # Patch signal handling, websocket connection, and thread pool executor
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.add_signal_handler = Mock()
            mock_loop.return_value.remove_signal_handler = Mock()

            # Mock the run_in_executor to run synchronously
            async def mock_executor(executor, func, *args):
                return func(*args)

            mock_loop.return_value.run_in_executor = mock_executor

            with patch("plldb.websocket_client.websockets.connect", new_callable=AsyncMock) as mock_connect:
                mock_connect.return_value = mock_ws

                await client.run_loop(handler)

        # Verify handler was called with correct messages
        assert handler.call_count == 2

        # Verify that responses were sent back
        assert mock_ws.send.call_count == 2
        sent_messages = [json.loads(call.args[0]) for call in mock_ws.send.call_args_list]
        assert sent_messages[0]["requestId"] == "req-1"
        assert sent_messages[0]["statusCode"] == 200
        assert sent_messages[0]["response"] == "response-1"
        assert sent_messages[1]["requestId"] == "req-2"
        assert sent_messages[1]["statusCode"] == 200
        assert sent_messages[1]["response"] == "response-2"

    @pytest.mark.asyncio
    async def test_run_loop_keyboard_interrupt(self):
        """Test loop termination on interrupt."""
        mock_ws = AsyncMock()

        client = WebSocketClient("wss://example.com/ws", "test-session-id")

        # Patch signal handling and websocket connection
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.add_signal_handler = Mock()
            mock_loop.return_value.remove_signal_handler = Mock()

            with patch("plldb.websocket_client.websockets.connect", new_callable=AsyncMock) as mock_connect:
                mock_connect.return_value = mock_ws

                # Stop the loop after first iteration
                client._running = False
                await client.run_loop()

        mock_ws.close.assert_called_once()

    def test_stop(self):
        """Test stopping the message loop."""
        client = WebSocketClient("wss://example.com/ws", "test-session-id")
        client._running = True

        client.stop()

        assert client._running is False

    @pytest.mark.asyncio
    async def test_run_loop_with_error_handler(self):
        """Test message loop with handler that raises exception."""
        # Mock WebSocket
        mock_ws = AsyncMock()
        messages = [
            json.dumps(
                {"requestId": "req-1", "sessionId": "test-session-id", "connectionId": "conn-1", "lambdaFunctionName": "test-function", "lambdaFunctionVersion": "$LATEST", "event": "test-event-1"}
            )
        ]
        mock_ws.recv.side_effect = messages + [websockets.exceptions.ConnectionClosed(None, None)]

        # Mock message handler that raises exception
        handler = Mock()
        handler.side_effect = Exception("Handler error")

        # Create client and run loop
        client = WebSocketClient("wss://example.com/ws", "test-session-id")

        # Patch signal handling, websocket connection, and thread pool executor
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.add_signal_handler = Mock()
            mock_loop.return_value.remove_signal_handler = Mock()

            # Mock the run_in_executor to run synchronously
            async def mock_executor(executor, func, *args):
                return func(*args)

            mock_loop.return_value.run_in_executor = mock_executor

            with patch("plldb.websocket_client.websockets.connect", new_callable=AsyncMock) as mock_connect:
                mock_connect.return_value = mock_ws

                await client.run_loop(handler)

        # Verify handler was called
        assert handler.call_count == 1

        # Verify that error response was sent back
        assert mock_ws.send.call_count == 1
        sent_message = json.loads(mock_ws.send.call_args[0][0])
        assert sent_message["requestId"] == "req-1"
        assert sent_message["statusCode"] == 500
        assert sent_message["response"] == ""
        assert sent_message["errorMessage"] == "Handler error"
