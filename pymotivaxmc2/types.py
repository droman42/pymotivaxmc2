"""
Type definitions for the eMotiva integration.

This module contains shared type definitions used throughout the package
to ensure type consistency and improve code maintainability.
"""

from typing import Dict, Any, Callable, Optional, Union
import socket

# Type aliases for better readability
DeviceCallback = Callable[[Dict[str, Any]], None]
SocketDict = Dict[int, socket.socket]
DeviceDict = Dict[str, DeviceCallback]
ResponseData = Dict[str, Any]
CommandParams = Optional[Dict[str, Any]]
CommandResponse = Union[Dict[str, Any], None]

# Configuration types
class EmotivaConfig:
    """Configuration class for Emotiva device settings."""
    
    def __init__(
        self,
        ip: str,
        timeout: int = 2,
        discover_request_port: int = 7000,
        discover_response_port: int = 7001,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> None:
        """
        Initialize Emotiva configuration.
        
        Args:
            ip (str): IP address of the Emotiva device
            timeout (int): Socket timeout in seconds
            discover_request_port (int): Port for discovery requests
            discover_response_port (int): Port for discovery responses
            max_retries (int): Maximum number of retries for failed operations
            retry_delay (float): Delay between retries in seconds
        """
        self.ip = ip
        self.timeout = timeout
        self.discover_request_port = discover_request_port
        self.discover_response_port = discover_response_port
        self.max_retries = max_retries
        self.retry_delay = retry_delay 