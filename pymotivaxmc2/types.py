"""
Type definitions for the eMotiva integration.

This module contains shared type definitions used throughout the package
to ensure type consistency and improve code maintainability.
"""

from typing import Dict, Any, Callable, Optional, Union, List
import socket
from .constants import DEFAULT_KEEPALIVE_INTERVAL, MAX_MISSED_KEEPALIVES

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
        notify_port: int = 7003,  # Port for device notifications
        max_retries: int = 3,
        retry_delay: float = 1.0,
        keepalive_interval: int = DEFAULT_KEEPALIVE_INTERVAL,
        max_missed_keepalives: int = MAX_MISSED_KEEPALIVES,
        default_subscriptions: Optional[List[str]] = None
    ) -> None:
        """
        Initialize Emotiva configuration.
        
        Args:
            ip (str): IP address of the Emotiva device
            timeout (int): Socket timeout in seconds
            discover_request_port (int): Port for discovery requests
            discover_response_port (int): Port for discovery responses
            notify_port (int): Port for device notifications
            max_retries (int): Maximum number of retries for failed operations
            retry_delay (float): Delay between retries in seconds
            keepalive_interval (int): Expected keepalive interval in milliseconds
            max_missed_keepalives (int): Maximum number of missed keepalives before considering device offline
            default_subscriptions (Optional[List[str]]): List of notification types to subscribe to by default
        """
        self.ip = ip
        self.timeout = timeout
        self.discover_request_port = discover_request_port
        self.discover_response_port = discover_response_port
        self.notify_port = notify_port
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.keepalive_interval = keepalive_interval
        self.max_missed_keepalives = max_missed_keepalives
        
        # Default subscriptions if none provided
        if default_subscriptions is None:
            self.default_subscriptions = [
                "power", "zone2_power", "volume", "input", "audio_bitstream", 
                "audio_bits", "video_input", "video_format", "mute", "mode"
            ]
        else:
            self.default_subscriptions = default_subscriptions 