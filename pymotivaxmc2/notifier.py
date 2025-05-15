"""
UDP notification system for Emotiva devices.

This module provides an asyncio-based notification system that listens for UDP messages
from Emotiva devices and routes them to registered callbacks. It implements the observer
pattern for flexible notification handling.
"""

import socket
import asyncio
import logging
import ipaddress
from typing import Dict, Callable, Set, Optional, List, Any, Tuple, Union, Generic, TypeVar, Protocol, cast
import time
import xml.etree.ElementTree as ET
from enum import Enum, auto
from abc import ABC, abstractmethod

from .protocol import ResponseParser
from .emotiva_types import (
    EmotivaNotification, 
    PropertyNotification, 
    MenuNotification, 
    BarDisplayNotification, 
    KeepAliveNotification, 
    GoodbyeNotification, 
    EmotivaNotificationListener,
    NotificationType as EmotivaNotificationType
)

_LOGGER = logging.getLogger(__name__)

class ConnectionState(Enum):
    """Connection states for the Emotiva device."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"

class NotificationType(Enum):
    """Types of notifications from Emotiva devices."""
    STANDARD = "standard"
    MENU = "menu"
    BAR = "bar"
    KEEPALIVE = "keepalive"
    GOODBYE = "goodbye"

class NotificationFilter:
    """Filter for notifications based on type, property name, etc."""
    
    def __init__(self, 
                notification_types: Optional[List[NotificationType]] = None,
                property_names: Optional[List[str]] = None,
                device_ips: Optional[List[str]] = None):
        """
        Initialize a notification filter.
        
        Args:
            notification_types: List of notification types to include
            property_names: List of property names to include
            device_ips: List of device IPs to include
        """
        self.notification_types = notification_types
        self.property_names = property_names
        self.device_ips = device_ips
    
    def matches(self, notification: EmotivaNotification) -> bool:
        """
        Check if a notification matches this filter.
        
        Args:
            notification: Notification to check
            
        Returns:
            True if notification matches filter, False otherwise
        """
        # Check device IP
        if self.device_ips and notification.device_ip not in self.device_ips:
            return False
            
        # Get equivalent EmotivaNotificationType from our internal NotificationType
        notification_type_map = {
            NotificationType.STANDARD: EmotivaNotificationType.PROPERTY,
            NotificationType.MENU: EmotivaNotificationType.MENU,
            NotificationType.BAR: EmotivaNotificationType.BAR,
            NotificationType.KEEPALIVE: EmotivaNotificationType.KEEPALIVE,
            NotificationType.GOODBYE: EmotivaNotificationType.GOODBYE
        }
        
        # Check notification type
        if self.notification_types:
            emtiva_types = [notification_type_map.get(nt) for nt in self.notification_types]
            if notification.notification_type not in emtiva_types:
                return False
            
        # For property notifications, check property name
        if (self.property_names and 
            notification.notification_type == EmotivaNotificationType.PROPERTY and
            isinstance(notification.data, dict) and
            'properties' in notification.data):
            
            # Check if any of the properties match
            properties = notification.data.get('properties', {})
            return any(prop_name in properties for prop_name in self.property_names)
            
        # All checks passed
        return True

class NotificationRegistry:
    """
    Registry for notification listeners.
    
    This class manages subscriptions to notifications, allowing listeners to
    register for specific types of notifications with optional filtering.
    """
    
    def __init__(self):
        """Initialize the notification registry."""
        # Map listeners to their filters
        self._listeners: Dict[EmotivaNotificationListener, List[NotificationFilter]] = {}
        self._lock = asyncio.Lock()
    
    async def register_listener(self, listener: EmotivaNotificationListener, 
                              filter_: Optional[NotificationFilter] = None) -> None:
        """
        Register a notification listener.
        
        Args:
            listener: The listener to register
            filter_: Optional filter for notifications
        """
        async with self._lock:
            if listener not in self._listeners:
                self._listeners[listener] = []
                
            if filter_:
                self._listeners[listener].append(filter_)
            
            _LOGGER.debug("Registered notification listener with %s filters", 
                         len(self._listeners[listener]))
    
    async def unregister_listener(self, listener: EmotivaNotificationListener) -> None:
        """
        Unregister a notification listener.
        
        Args:
            listener: The listener to unregister
        """
        async with self._lock:
            if listener in self._listeners:
                self._listeners.pop(listener)
                _LOGGER.debug("Unregistered notification listener")
    
    async def notify(self, notification: EmotivaNotification) -> None:
        """
        Notify all matching listeners of a notification.
        
        Args:
            notification: The notification to dispatch
        """
        async with self._lock:
            for listener, filters in self._listeners.items():
                # If no filters, always notify
                if not filters:
                    try:
                        listener.on_notification(notification)
                    except Exception as e:
                        _LOGGER.error("Error in notification listener: %s", e)
                    continue
                
                # Check if any filter matches
                for filter_ in filters:
                    if filter_.matches(notification):
                        try:
                            listener.on_notification(notification)
                        except Exception as e:
                            _LOGGER.error("Error in notification listener: %s", e)
                        break  # Don't notify the same listener multiple times

class NotificationParser:
    """
    Parser for Emotiva notification packets.
    
    This class parses raw notification data into structured notification objects.
    """
    
    @staticmethod
    def parse_notification(data: bytes, sender_ip: str) -> Optional[EmotivaNotification]:
        """
        Parse a notification packet.
        
        Args:
            data: Raw notification data
            sender_ip: IP address of the sender
            
        Returns:
            Parsed notification object or None if parsing failed
        """
        try:
            # Parse the XML
            root = ET.fromstring(data.decode('utf-8'))
            
            # Check the root tag
            if root.tag == 'emotivaNotify':
                # Look for special notification types
                for child in root:
                    # Check for keepalive
                    if (child.tag == 'property' and child.get('name') == 'keepalive') or child.tag == 'keepalive':
                        return KeepAliveNotification(sender_ip, EmotivaNotificationType.KEEPALIVE, None)
                    
                    # Check for goodbye
                    if (child.tag == 'property' and child.get('name') == 'goodbye') or child.tag == 'goodbye':
                        return GoodbyeNotification(sender_ip, EmotivaNotificationType.GOODBYE, None)
                
                # Standard property notification - collect all properties
                properties: Dict[str, Dict[str, Any]] = {}
                for child in root:
                    if child.tag == 'property':
                        name = child.get('name', '')
                        if name:
                            properties[name] = dict(child.attrib)
                    else:
                        # Legacy format where property name is the tag
                        properties[child.tag] = dict(child.attrib)
                
                return PropertyNotification(
                    sender_ip, 
                    EmotivaNotificationType.PROPERTY,
                    {
                        'sequence': root.get('sequence', '0'),
                        'properties': properties
                    }
                )
                
            elif root.tag == 'emotivaMenuNotify':
                # Menu notification
                menu_data = {
                    'sequence': root.get('sequence', '0'),
                    'rows': []
                }
                
                # Process menu rows
                for row in root.findall('row'):
                    row_data = {
                        'number': row.get('number', '0'),
                        'columns': []
                    }
                    
                    # Process columns
                    for col in row.findall('col'):
                        col_data = dict(col.attrib)
                        row_data['columns'].append(col_data)
                    
                    menu_data['rows'].append(row_data)
                
                return MenuNotification(sender_ip, EmotivaNotificationType.MENU, menu_data)
                
            elif root.tag == 'emotivaBarNotify':
                # Bar notification
                bar_data = {
                    'sequence': root.get('sequence', '0'),
                    'bars': []
                }
                
                # Process bars
                for bar in root.findall('bar'):
                    bar_type = bar.get('type', '')
                    
                    # Create bar info based on type
                    if bar_type == 'off':
                        bar_data['bars'].append({'type': 'off'})
                    elif bar_type == 'bigText':
                        bar_data['bars'].append({
                            'type': 'bigText',
                            'text': bar.get('text', '')
                        })
                    elif bar_type == 'bar':
                        bar_data['bars'].append({
                            'type': 'bar',
                            'text': bar.get('text', ''),
                            'value': bar.get('value', '0'),
                            'min': bar.get('min', '0'),
                            'max': bar.get('max', '100'),
                            'units': bar.get('units', '')
                        })
                
                return BarDisplayNotification(sender_ip, EmotivaNotificationType.BAR, bar_data)
                
        except Exception as e:
            _LOGGER.warning("Error parsing notification: %s", e)
            
        return None

class NotificationDispatcher:
    """
    Dispatches notifications to registered listeners.
    
    This class handles the parsing and routing of notifications to the appropriate listeners.
    """
    
    def __init__(self, registry: NotificationRegistry):
        """
        Initialize the notification dispatcher.
        
        Args:
            registry: The notification registry to use
        """
        self.registry = registry
        self._lock = asyncio.Lock()
    
    async def dispatch_notification(self, data: bytes, sender_ip: str) -> None:
        """
        Dispatch a notification to registered listeners.
        
        Args:
            data: Raw notification data
            sender_ip: IP address of the sender
        """
        # Parse the notification
        notification = NotificationParser.parse_notification(data, sender_ip)
        
        if notification:
            # Notify all matching listeners
            await self.registry.notify(notification)
