#!/usr/bin/env python
"""
Notification System Example

This example demonstrates how to use the new notification system
in the pymotivaxmc2 package. It shows how to create custom notification
listeners and handle different types of notifications.
"""

import asyncio
import logging
import sys
from typing import Dict, Any, Optional, List, Callable

from pymotivaxmc2.notifier import (
    NotificationRegistry, NotificationDispatcher,
    NotificationFilter, NotificationType
)
from pymotivaxmc2.emotiva_types import (
    EmotivaNotification, PropertyNotification,
    MenuNotification, BarDisplayNotification,
    EmotivaNotificationListener, NotificationType as EmotivaNotificationType,
    BarNotification, BarType, EmotivaConfig
)
from pymotivaxmc2.controller import EmotivaController

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
_LOGGER = logging.getLogger(__name__)

class VolumeNotificationListener(EmotivaNotificationListener):
    """
    Example listener that only processes volume-related notifications.
    """
    
    def on_notification(self, notification: EmotivaNotification) -> None:
        """Handle a notification from the device."""
        if isinstance(notification, PropertyNotification):
            properties = notification.data.get('properties', {})
            if 'volume' in properties:
                volume_data = properties['volume']
                _LOGGER.info(f"Volume change: {volume_data}")

class MenuDisplayListener(EmotivaNotificationListener):
    """
    Example listener that processes menu notifications.
    """
    
    def on_notification(self, notification: EmotivaNotification) -> None:
        """Handle a notification from the device."""
        if isinstance(notification, MenuNotification):
            menu_data = notification.data
            _LOGGER.info(f"Menu update: {len(menu_data.get('rows', []))} rows")
            
            # Print each row
            for row in menu_data.get('rows', []):
                row_number = row.get('number', '0')
                columns = row.get('columns', [])
                column_texts = []
                for col in columns:
                    text = col.get('text', '')
                    column_texts.append(text)
                _LOGGER.info(f"  Row {row_number}: {' | '.join(column_texts)}")

class BarDisplayListener(EmotivaNotificationListener):
    """
    Example listener that processes bar notifications (like volume display).
    """
    
    def __init__(self):
        self.last_notifications: List[BarNotification] = []
    
    def on_notification(self, notification: EmotivaNotification) -> None:
        """Handle a notification from the device."""
        if isinstance(notification, BarDisplayNotification):
            bar_data = notification.data
            _LOGGER.info(f"Bar display update: {len(bar_data.get('bars', []))} bars")
            
            # Process and convert to BarNotification objects
            bar_notifications = []
            for i, bar_info in enumerate(bar_data.get('bars', [])):
                bar_type_str = bar_info.get('type', 'off')
                
                # Convert to bar_type string
                bar_type = "off"
                if bar_type_str == 'bigText':
                    bar_type = "text"
                elif bar_type_str == 'bar':
                    bar_type = "bar"
                    
                # Create bar notification
                bar_notification = BarNotification(
                    bar_id=i,
                    bar_type=bar_type,
                    text=bar_info.get('text', ''),
                    value=float(bar_info.get('value', 0)),
                    min_value=float(bar_info.get('min', 0)),
                    max_value=float(bar_info.get('max', 100)),
                    units=bar_info.get('units', '')
                )
                
                bar_notifications.append(bar_notification)
                _LOGGER.info(f"  Bar: {bar_notification}")
                
            self.last_notifications = bar_notifications

class AllNotificationsListener(EmotivaNotificationListener):
    """
    Example listener that logs all notifications.
    """
    
    def on_notification(self, notification: EmotivaNotification) -> None:
        """Handle a notification from the device."""
        _LOGGER.info(f"Received {notification.notification_type.value} notification from {notification.device_ip}")
        
        # Different handling based on notification type
        if isinstance(notification, PropertyNotification):
            properties = notification.data.get('properties', {})
            _LOGGER.info(f"  Properties: {', '.join(properties.keys())}")
            
        elif isinstance(notification, MenuNotification):
            menu_data = notification.data
            _LOGGER.info(f"  Menu: {len(menu_data.get('rows', []))} rows")
            
        elif isinstance(notification, BarDisplayNotification):
            bar_data = notification.data
            _LOGGER.info(f"  Bar display: {len(bar_data.get('bars', []))} bars")
            
        elif isinstance(notification, EmotivaNotification):
            # Generic case for other notification types
            _LOGGER.info(f"  Data: {notification.data}")

async def legacy_callback(data: Dict[str, Any]) -> None:
    """
    Example of a legacy callback format for backward compatibility.
    
    Args:
        data: Notification data in dictionary format
    """
    _LOGGER.info(f"Legacy callback received data: {list(data.keys())}")

# Simple synchronous wrapper for async callback
def sync_legacy_callback_wrapper(data: Dict[str, Any]) -> None:
    """Synchronous wrapper that schedules the async callback."""
    asyncio.create_task(legacy_callback(data))

# Create an adapter for legacy callbacks
class EmotivaAdapter(EmotivaNotificationListener):
    """
    Adapter to convert EmotivaNotification to legacy callback format.
    """
    
    def __init__(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Initialize adapter with a legacy callback.
        
        Args:
            callback: Legacy callback function
        """
        self.callback = callback
        
    def on_notification(self, notification: EmotivaNotification) -> None:
        """
        Handle notification by converting to legacy format and calling callback.
        
        Args:
            notification: The notification to handle
        """
        # Convert notification to dict format
        if hasattr(notification, 'data') and notification.data:
            self.callback(notification.data)

async def main() -> None:
    """
    Run the notification example.
    
    This function demonstrates:
    1. Creating a notification registry
    2. Registering different types of listeners
    3. Creating filters for specific notification types
    4. Dispatching notifications
    5. Using the adapter pattern for backward compatibility
    """
    # Create notification registry and dispatcher
    registry = NotificationRegistry()
    dispatcher = NotificationDispatcher(registry)
    
    # Create listeners
    volume_listener = VolumeNotificationListener()
    menu_listener = MenuDisplayListener()
    bar_listener = BarDisplayListener()
    all_listener = AllNotificationsListener()
    
    # Register listeners with different filters
    
    # Volume listener with filter for volume properties
    volume_filter = NotificationFilter(
        notification_types=[NotificationType.STANDARD],
        property_names=["volume"]
    )
    await registry.register_listener(volume_listener, volume_filter)
    
    # Menu listener with filter for menu notifications
    menu_filter = NotificationFilter(
        notification_types=[NotificationType.MENU]
    )
    await registry.register_listener(menu_listener, menu_filter)
    
    # Bar listener with filter for bar notifications
    bar_filter = NotificationFilter(
        notification_types=[NotificationType.BAR]
    )
    await registry.register_listener(bar_listener, bar_filter)
    
    # All listener without filter receives everything
    await registry.register_listener(all_listener)
    
    # Example: Create an adapter for legacy callback
    adapter = EmotivaAdapter(sync_legacy_callback_wrapper)
    await registry.register_listener(adapter)
    
    # Example usage with an actual device
    device_ip = "192.168.1.100"  # Replace with your device IP
    
    try:
        # Try to connect to a real device if specified
        if len(sys.argv) > 1:
            device_ip = sys.argv[1]
            
            # Create config and initialize emotiva
            config = EmotivaConfig(ip=device_ip)
            emotiva = EmotivaController(config)
            
            # Wait for initialization
            _LOGGER.info(f"Connecting to Emotiva device at {device_ip}...")
            await emotiva.initialize()
            
            # For now, just wait for notifications without registering callbacks
            # EmotivaController might not have register_bar_callback method
            
            # Run for 60 seconds to receive notifications
            _LOGGER.info("Running for 60 seconds to receive notifications...")
            await asyncio.sleep(60)
            
        else:
            # If no device IP provided, demonstrate with mock notifications
            _LOGGER.info("No device IP provided. Demonstrating with mock notifications...")
            
            # Example: Create and dispatch a property notification
            property_data = {
                'sequence': '1234',
                'properties': {
                    'volume': {
                        'value': '75',
                        'min': '0',
                        'max': '100',
                        'units': 'dB'
                    },
                    'power': {
                        'value': 'on'
                    }
                }
            }
            property_notification = PropertyNotification(
                device_ip, EmotivaNotificationType.PROPERTY, property_data
            )
            await registry.notify(property_notification)
            
            # Example: Create and dispatch a menu notification
            menu_data = {
                'sequence': '1235',
                'rows': [
                    {
                        'number': '1',
                        'columns': [
                            {'text': 'Main Menu', 'flags': 'highlight'},
                            {'text': 'Options', 'flags': ''}
                        ]
                    },
                    {
                        'number': '2',
                        'columns': [
                            {'text': 'Audio Settings', 'flags': ''},
                            {'text': '>', 'flags': ''}
                        ]
                    }
                ]
            }
            menu_notification = MenuNotification(
                device_ip, EmotivaNotificationType.MENU, menu_data
            )
            await registry.notify(menu_notification)
            
            # Example: Create and dispatch a bar notification
            bar_data = {
                'sequence': '1236',
                'bars': [
                    {
                        'type': 'bar',
                        'text': 'Volume',
                        'value': '75',
                        'min': '0',
                        'max': '100',
                        'units': 'dB'
                    }
                ]
            }
            bar_notification = BarDisplayNotification(
                device_ip, EmotivaNotificationType.BAR, bar_data
            )
            await registry.notify(bar_notification)
            
            # Wait a moment to let all callbacks complete
            await asyncio.sleep(1)
    
    except Exception as e:
        _LOGGER.error(f"Error: {e}")
    
    finally:
        # Cleanup
        _LOGGER.info("Example completed")

if __name__ == "__main__":
    asyncio.run(main()) 