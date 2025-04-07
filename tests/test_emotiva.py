"""
Tests for the Emotiva integration.

This module contains unit tests for the Emotiva device control functionality.
"""

import unittest
from unittest.mock import patch, MagicMock
import socket
from pymotiva import Emotiva, EmotivaConfig
from pymotiva.exceptions import (
    InvalidTransponderResponseError,
    InvalidSourceError,
    InvalidModeError
)

class TestEmotiva(unittest.TestCase):
    """Test cases for the Emotiva class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = EmotivaConfig(ip="192.168.1.100")
        self.emotiva = Emotiva(self.config)
        
    def test_initialization(self):
        """Test Emotiva initialization."""
        self.assertEqual(self.emotiva._ip, "192.168.1.100")
        self.assertEqual(self.emotiva._timeout, 2)
        self.assertIsNone(self.emotiva._transponder_port)
        self.assertIsNone(self.emotiva._callback)
        
    @patch('socket.socket')
    def test_discover_success(self, mock_socket):
        """Test successful device discovery."""
        # Mock socket instance
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        
        # Mock response data
        mock_sock.recvfrom.return_value = (
            b'<Response><Discover port="7002"/></Response>',
            ('192.168.1.100', 7001)
        )
        
        # Test discovery
        port = self.emotiva.discover()
        self.assertEqual(port, 7002)
        
        # Verify socket operations
        mock_sock.bind.assert_called_once()
        mock_sock.sendto.assert_called_once()
        mock_sock.recvfrom.assert_called_once()
        mock_sock.close.assert_called_once()
        
    @patch('socket.socket')
    def test_discover_timeout(self, mock_socket):
        """Test device discovery timeout."""
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_sock.recvfrom.side_effect = socket.timeout()
        
        with self.assertRaises(InvalidTransponderResponseError):
            self.emotiva.discover()
            
    def test_set_callback(self):
        """Test setting notification callback."""
        def mock_callback(data):
            pass
            
        self.emotiva.set_callback(mock_callback)
        self.assertEqual(self.emotiva._callback, mock_callback)
        
    @patch('socket.socket')
    def test_send_command_success(self, mock_socket):
        """Test successful command sending."""
        # Setup
        self.emotiva._transponder_port = 7002
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        
        # Mock response
        mock_sock.recvfrom.return_value = (
            b'<Response><Power value="on"/></Response>',
            ('192.168.1.100', 7002)
        )
        
        # Test command
        response = self.emotiva.send_command("power", {"value": "on"})
        self.assertIsNotNone(response)
        
        # Verify socket operations
        mock_sock.sendto.assert_called_once()
        mock_sock.recvfrom.assert_called_once()
        mock_sock.close.assert_called_once()
        
    def test_send_command_not_discovered(self):
        """Test sending command before discovery."""
        with self.assertRaises(InvalidTransponderResponseError):
            self.emotiva.send_command("power", {"value": "on"})

if __name__ == '__main__':
    unittest.main() 