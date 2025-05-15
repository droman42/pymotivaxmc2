"""
Type definitions for the Emotiva integration.

This module defines data structures and type hints used throughout the Emotiva integration.
"""

from typing import Dict, Any, Callable, Optional, Union, List, Protocol, TypeVar, Generic, Set, Tuple, Coroutine
import socket
import time
from enum import Enum, auto
from .constants import DEFAULT_KEEPALIVE_INTERVAL
from dataclasses import dataclass, field

# Type aliases for better readability
DeviceCallback = Callable[[str, Dict[str, Any]], None]
SocketDict = Dict[int, socket.socket]
DeviceDict = Dict[str, DeviceCallback]
ResponseData = Dict[str, Any]
CommandParams = Optional[Dict[str, Any]]
CommandResponse = Union[Dict[str, Any], None]

class ConnectionState(Enum):
    """Connection states for an Emotiva device."""
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    ERROR = "error"
    
class NotificationType(Enum):
    """Types of notifications that can be received from an Emotiva device."""
    PROPERTY = auto()
    MENU = auto()
    BAR = auto()
    KEEPALIVE = auto()
    GOODBYE = auto()
    
class BarType(Enum):
    """Types of bar notifications that can be received."""
    OFF = "off"
    BAR = "bar"
    TEXT = "text"
    SUBTEXT = "subtext"

@dataclass
class BarNotification:
    """Information about a bar notification."""
    bar_id: int
    bar_type: str
    text: str
    value: float = 0.0
    min_value: float = 0.0
    max_value: float = 100.0
    units: str = ""

# Type for notification data
T = TypeVar('T')

class EmotivaNotification(Generic[T]):
    """Base class for all Emotiva notifications."""
    
    def __init__(self, device_ip: str, notification_type: NotificationType, data: T):
        """
        Initialize a notification object.
        
        Args:
            device_ip: IP address of the device that sent the notification
            notification_type: Type of notification
            data: Notification data (type depends on notification type)
        """
        self.device_ip = device_ip
        self.notification_type = notification_type
        self.data = data
        self.timestamp = time.time()

class PropertyNotification(EmotivaNotification[Dict[str, Any]]):
    """Notification containing property updates."""
    properties: Dict[str, Any] = field(default_factory=dict)

class MenuNotification(EmotivaNotification[Dict[str, Any]]):
    """Notification containing menu updates."""
    menu_id: str = ""
    items: List[Dict[str, Any]] = field(default_factory=list)
    position: int = 0

class BarDisplayNotification(EmotivaNotification[Dict[str, Any]]):
    """Notification containing bar display updates."""
    bars: List[BarNotification] = field(default_factory=list)

class KeepAliveNotification(EmotivaNotification[None]):
    """Notification sent periodically to keep the connection alive."""
    pass

class GoodbyeNotification(EmotivaNotification[None]):
    """Notification sent when the device is shutting down."""
    pass

class EmotivaNotificationListener(Protocol):
    """Protocol for notification listeners."""
    
    def on_notification(self, notification: EmotivaNotification) -> None:
        """
        Handle a notification from a device.
        
        Args:
            notification: The notification object
        """
        ...

# Configuration types
@dataclass
class EmotivaConfig:
    """Configuration for an Emotiva device connection."""
    ip: str = ""
    command_port: int = 7000
    notification_port: int = 7001
    timeout: float = 2.0
    retry_delay: float = 1.0
    max_retries: int = 3
    keepalive_interval: int = 30
    default_subscriptions: List[str] = field(default_factory=list)

class StateChangeListener:
    """Interface for objects that can receive state change notifications."""
    
    def on_state_change(self, property_name: str, old_value: Any, new_value: Any) -> None:
        """
        Handle a state change notification.
        
        Args:
            property_name: Name of the property that changed
            old_value: Previous value of the property
            new_value: New value of the property
        """
        pass

# Type aliases for callbacks
PropertyCallback = Callable[[str, Any, Any], Union[None, Coroutine[Any, Any, None]]]
NotificationCallback = Callable[[EmotivaNotification], None]
ConnectionCallback = Callable[[str, ConnectionState], None]
MenuCallback = Callable[[Dict[str, Any]], None]
BarCallback = Callable[[List[BarNotification]], None] 