import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
import websockets

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
        messages = ['{"type": "message1"}', '{"type": "message2"}']
        mock_ws.recv.side_effect = messages + [websockets.exceptions.ConnectionClosed(None, None)]

        # Mock message handler
        handler = Mock()

        # Create client and run loop
        client = WebSocketClient("wss://example.com/ws", "test-session-id")

        # Patch signal handling and websocket connection
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.add_signal_handler = Mock()
            mock_loop.return_value.remove_signal_handler = Mock()

            with patch("plldb.websocket_client.websockets.connect", new_callable=AsyncMock) as mock_connect:
                mock_connect.return_value = mock_ws

                await client.run_loop(handler)

        # Verify handler was called
        assert handler.call_count == 2
        handler.assert_any_call({"type": "message1"})
        handler.assert_any_call({"type": "message2"})

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
