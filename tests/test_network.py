"""
Tests for the network module.

This module contains unit tests for the network component of the Emotiva integration.
"""

import unittest
import asyncio
import socket
from unittest.mock import patch, MagicMock, call
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, Tuple

from pymotivaxmc2.network import (
    SocketManager,
    EmotivaNetworkDiscovery,
    BroadcastListener,
    ConnectionManager,
    CommandExecutor,
    ConnectionState,
    NetworkDevice
)
from pymotivaxmc2.protocol import ProtocolVersion, TransponderResponse


class TestSocketManager(unittest.TestCase):
    """Test the SocketManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.socket_manager = SocketManager(timeout=0.1)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def tearDown(self):
        """Clean up after tests."""
        self.loop.run_until_complete(self.socket_manager.cleanup())
        self.loop.close()
    
    @patch('socket.socket')
    def test_get_socket(self, mock_socket):
        """Test getting or creating a socket."""
        # Setup mock
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        
        # Get a socket
        sock = self.loop.run_until_complete(
            self.socket_manager.get_socket('192.168.1.100', 7000)
        )
        
        # Verify socket was created and configured
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        mock_sock.settimeout.assert_called_once_with(0.1)
        self.assertEqual(sock, mock_sock)
        
        # Try getting the same socket again
        sock2 = self.loop.run_until_complete(
            self.socket_manager.get_socket('192.168.1.100', 7000)
        )
        
        # Verify the same socket was returned
        self.assertEqual(sock2, mock_sock)
        mock_socket.assert_called_once()  # Only called once
    
    @patch('socket.socket')
    def test_send_packet(self, mock_socket):
        """Test sending a packet."""
        # Setup mock
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        
        # Send a packet
        data = b'test data'
        self.loop.run_until_complete(
            self.socket_manager.send_packet('192.168.1.100', 7000, data)
        )
        
        # Verify the packet was sent
        mock_sock.sendto.assert_called_once_with(data, ('192.168.1.100', 7000))
    
    @patch('socket.socket')
    def test_receive_packet(self, mock_socket):
        """Test receiving a packet."""
        # Setup mock
        mock_sock = MagicMock()
        mock_sock.recvfrom.return_value = (b'response data', ('192.168.1.100', 7000))
        mock_socket.return_value = mock_sock
        
        # Receive a packet
        response = self.loop.run_until_complete(
            self.socket_manager.receive_packet('192.168.1.100', 7000, timeout=0.5)
        )
        
        # Verify the response
        self.assertEqual(response, b'response data')
        mock_sock.settimeout.assert_called_with(0.5)
    
    @patch('socket.socket')
    def test_receive_packet_timeout(self, mock_socket):
        """Test receiving a packet with timeout."""
        # Setup mock
        mock_sock = MagicMock()
        mock_sock.recvfrom.side_effect = socket.timeout
        mock_socket.return_value = mock_sock
        
        # Receive a packet
        response = self.loop.run_until_complete(
            self.socket_manager.receive_packet('192.168.1.100', 7000)
        )
        
        # Verify the response is None
        self.assertIsNone(response)
    
    @patch('asyncio.DatagramProtocol')
    @patch('asyncio.BaseEventLoop.create_datagram_endpoint')
    def test_create_listening_socket(self, mock_create_endpoint, mock_protocol):
        """Test creating a listening socket."""
        # Setup mocks
        mock_transport = MagicMock()
        mock_create_endpoint.return_value = (mock_transport, MagicMock())
        
        # Create a listening socket
        callback = MagicMock()
        self.loop.run_until_complete(
            self.socket_manager.create_listening_socket(7000, callback)
        )
        
        # Verify the socket was created
        mock_create_endpoint.assert_called_once()
        # Check the local_addr parameter
        local_addr = mock_create_endpoint.call_args[1]['local_addr']
        self.assertEqual(local_addr, ('', 7000))
    
    @patch('asyncio.DatagramProtocol')
    @patch('asyncio.BaseEventLoop.create_datagram_endpoint')
    def test_register_device(self, mock_create_endpoint, mock_protocol):
        """Test registering a device."""
        # Setup mocks
        mock_transport = MagicMock()
        mock_create_endpoint.return_value = (mock_transport, MagicMock())
        
        # Register a device
        callback = MagicMock()
        self.loop.run_until_complete(
            self.socket_manager.register_device('192.168.1.100', 7000, callback)
        )
        
        # Verify the device was registered
        self.assertEqual(self.socket_manager._callbacks.get('192.168.1.100'), callback)
        mock_create_endpoint.assert_called_once()


class TestEmotivaNetworkDiscovery(unittest.TestCase):
    """Test the EmotivaNetworkDiscovery class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.socket_manager = MagicMock()
        self.discovery = EmotivaNetworkDiscovery(self.socket_manager)
        
        # Create a patched version of several functions we need to control
        self.patch_socket = patch('socket.socket')
        self.mock_socket = self.patch_socket.start()
        
        self.patch_select = patch('select.select')
        self.mock_select = self.patch_select.start()
        
        self.patch_parser = patch('pymotivaxmc2.protocol.ResponseParser')
        self.mock_parser = self.patch_parser.start()
        
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def tearDown(self):
        """Clean up after tests."""
        self.patch_socket.stop()
        self.patch_select.stop()
        self.patch_parser.stop()
        self.loop.close()
    
    def test_discover_devices(self):
        """Test discovering devices on the network."""
        # Setup mocks
        mock_broadcast_sock = MagicMock()
        mock_resp_sock = MagicMock()
        
        # Make the socket constructor return our mocks
        self.mock_socket.side_effect = [mock_broadcast_sock, mock_resp_sock]
        
        # Make select return our receive socket as ready to read
        self.mock_select.return_value = ([mock_resp_sock], [], [])
        
        # Mock the receive of a transponder response
        mock_resp_sock.recvfrom.return_value = (b'<transponder data>', ('192.168.1.100', 7000))
        
        # Mock the response parsing
        mock_doc = MagicMock()
        self.mock_parser.parse_response.return_value = mock_doc
        
        mock_transponder = MagicMock()
        mock_transponder.name = "Test Device"
        mock_transponder.model = "XMC-1"
        mock_transponder.version = "3.1"
        mock_transponder.ports = {"controlPort": 7002}
        mock_transponder.keepalive_interval = 30000
        
        self.mock_parser.parse_transponder_response.return_value = mock_transponder
        
        # Discover devices
        devices = self.loop.run_until_complete(
            self.discovery.discover_devices(timeout=0.1, attempts=1)
        )
        
        # Verify discovery request was sent
        mock_broadcast_sock.sendto.assert_called_once()
        
        # Verify response was handled
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].ip, '192.168.1.100')
        self.assertEqual(devices[0].name, 'Test Device')
        self.assertEqual(devices[0].model, 'XMC-1')
        self.assertEqual(devices[0].protocol_version, '3.1')
        self.assertEqual(devices[0].ports, {"controlPort": 7002})
        self.assertEqual(devices[0].keepalive_interval, 30000)


class TestBroadcastListener(unittest.TestCase):
    """Test the BroadcastListener class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.socket_manager = MagicMock()
        self.listener = BroadcastListener(self.socket_manager)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def tearDown(self):
        """Clean up after tests."""
        self.loop.close()
    
    def test_start(self):
        """Test starting the broadcast listener."""
        # Start the listener
        self.loop.run_until_complete(self.listener.start(7000))
        
        # Verify a listening socket was created
        self.socket_manager.create_listening_socket.assert_called_once()
        self.assertTrue(self.listener._running)
    
    def test_stop(self):
        """Test stopping the broadcast listener."""
        # Start and then stop the listener
        self.loop.run_until_complete(self.listener.start(7000))
        self.loop.run_until_complete(self.listener.stop())
        
        # Verify the socket was closed
        self.socket_manager.close_listening_socket.assert_called_once_with(7000)
        self.assertFalse(self.listener._running)
    
    @patch('pymotivaxmc2.protocol.ResponseParser')
    def test_handle_broadcast(self, mock_parser):
        """Test handling a broadcast message."""
        # Setup mocks
        mock_doc = MagicMock()
        mock_parser.parse_response.return_value = mock_doc
        
        mock_transponder = MagicMock()
        mock_transponder.name = "Test Device"
        mock_transponder.model = "XMC-1"
        mock_transponder.version = "3.1"
        mock_transponder.ports = {"controlPort": 7002}
        mock_transponder.keepalive_interval = 30000
        
        mock_parser.parse_transponder_response.return_value = mock_transponder
        
        # Register a callback
        callback = MagicMock()
        self.listener.register_callback(callback)
        
        # Simulate receiving a broadcast
        addr = ('192.168.1.100', 7000)
        data = b'<transponder data>'
        self.loop.run_until_complete(self.listener._handle_broadcast(data, addr))
        
        # Verify the callback was called with a device
        callback.assert_called_once()
        device = callback.call_args[0][0]
        self.assertEqual(device.ip, '192.168.1.100')
        self.assertEqual(device.name, 'Test Device')
        self.assertEqual(device.model, 'XMC-1')


class TestConnectionManager(unittest.TestCase):
    """Test the ConnectionManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.socket_manager = MagicMock()
        self.connection_manager = ConnectionManager(self.socket_manager)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def tearDown(self):
        """Clean up after tests."""
        self.loop.run_until_complete(self.connection_manager.cleanup())
        self.loop.close()
    
    def test_register_device(self):
        """Test registering a device for connection monitoring."""
        # Register a device
        self.loop.run_until_complete(
            self.connection_manager.register_device('192.168.1.100', 30000)
        )
        
        # Verify the device was registered
        self.assertEqual(
            self.connection_manager._keepalive_intervals.get('192.168.1.100'), 
            30000
        )
        self.assertEqual(
            self.connection_manager._connection_states.get('192.168.1.100'),
            ConnectionState.DISCONNECTED
        )
        
        # Verify monitoring was started
        self.assertIn('192.168.1.100', self.connection_manager._monitoring_tasks)
        self.assertFalse(self.connection_manager._monitoring_tasks['192.168.1.100'].done())
    
    def test_update_activity(self):
        """Test updating device activity."""
        # Register a device
        self.loop.run_until_complete(
            self.connection_manager.register_device('192.168.1.100', 30000)
        )
        
        # Initial state should be DISCONNECTED
        self.assertEqual(
            self.connection_manager._connection_states.get('192.168.1.100'),
            ConnectionState.DISCONNECTED
        )
        
        # Update activity
        self.loop.run_until_complete(
            self.connection_manager.update_activity('192.168.1.100')
        )
        
        # State should now be CONNECTED
        self.assertEqual(
            self.connection_manager._connection_states.get('192.168.1.100'),
            ConnectionState.CONNECTED
        )
    
    def test_register_callback(self):
        """Test registering a connection state callback."""
        # Setup a callback
        callback = MagicMock()
        
        # Register a device
        self.loop.run_until_complete(
            self.connection_manager.register_device('192.168.1.100', 30000)
        )
        
        # Register a callback
        self.loop.run_until_complete(
            self.connection_manager.register_callback('192.168.1.100', callback)
        )
        
        # Verify callback was registered
        self.assertIn(callback, self.connection_manager._callbacks.get('192.168.1.100', []))
        
        # Verify callback was called with initial state
        callback.assert_called_once_with('192.168.1.100', ConnectionState.DISCONNECTED)
        
        # Update activity to change state
        callback.reset_mock()
        self.loop.run_until_complete(
            self.connection_manager.update_activity('192.168.1.100')
        )
        
        # Verify callback was called with new state
        callback.assert_called_once_with('192.168.1.100', ConnectionState.CONNECTED)


class TestCommandExecutor(unittest.TestCase):
    """Test the CommandExecutor class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.socket_manager = MagicMock()
        self.command_executor = CommandExecutor(self.socket_manager)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def tearDown(self):
        """Clean up after tests."""
        self.loop.close()
    
    def test_execute_command_success(self):
        """Test successful command execution."""
        # Setup mock responses
        self.socket_manager.send_packet = AsyncMock()
        self.socket_manager.receive_packet = AsyncMock(return_value=b'response data')
        
        # Execute a command
        response = self.loop.run_until_complete(
            self.command_executor.execute_command(
                '192.168.1.100', 7002, b'command data', retries=3, timeout=0.5
            )
        )
        
        # Verify command was sent
        self.socket_manager.send_packet.assert_called_once_with(
            '192.168.1.100', 7002, b'command data'
        )
        
        # Verify response was received
        self.socket_manager.receive_packet.assert_called_once_with(
            '192.168.1.100', 7002, timeout=0.5
        )
        
        # Verify the response
        self.assertEqual(response, b'response data')
    
    def test_execute_command_retry(self):
        """Test command execution with retry."""
        # Setup mock responses
        self.socket_manager.send_packet = AsyncMock()
        
        # First attempt fails, second succeeds
        self.socket_manager.receive_packet = AsyncMock(side_effect=[None, b'response data'])
        
        # Execute a command
        response = self.loop.run_until_complete(
            self.command_executor.execute_command(
                '192.168.1.100', 7002, b'command data', retries=3, timeout=0.1
            )
        )
        
        # Verify command was sent twice
        self.assertEqual(self.socket_manager.send_packet.call_count, 2)
        
        # Verify response was attempted to be received twice
        self.assertEqual(self.socket_manager.receive_packet.call_count, 2)
        
        # Verify the response
        self.assertEqual(response, b'response data')
    
    def test_execute_command_all_retries_fail(self):
        """Test command execution with all retries failing."""
        # Setup mock responses
        self.socket_manager.send_packet = AsyncMock()
        
        # All attempts return None (timeout)
        self.socket_manager.receive_packet = AsyncMock(return_value=None)
        
        # Execute a command
        response = self.loop.run_until_complete(
            self.command_executor.execute_command(
                '192.168.1.100', 7002, b'command data', retries=2, timeout=0.1
            )
        )
        
        # Verify command was sent for each retry
        self.assertEqual(self.socket_manager.send_packet.call_count, 2)
        
        # Verify response was attempted to be received for each retry
        self.assertEqual(self.socket_manager.receive_packet.call_count, 2)
        
        # Verify the response is None
        self.assertIsNone(response)
    
    def test_execute_command_error(self):
        """Test command execution with error."""
        # Setup mock responses
        self.socket_manager.send_packet = AsyncMock(side_effect=OSError("Network error"))
        
        # Execute a command
        with self.assertRaises(OSError):
            self.loop.run_until_complete(
                self.command_executor.execute_command(
                    '192.168.1.100', 7002, b'command data', retries=1, timeout=0.1
                )
            )
        
        # Verify command was attempted to be sent
        self.socket_manager.send_packet.assert_called_once()


class AsyncMock(MagicMock):
    """Mock for async functions."""
    
    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)


if __name__ == '__main__':
    unittest.main() 