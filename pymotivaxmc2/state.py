"""
State Management Module for Emotiva Integration.

This module provides classes for tracking device state, handling property changes,
and managing device configuration.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Set, Callable, Union, cast

from .emotiva_types import StateChangeListener, PropertyCallback
from .exceptions import StateValidationError

_LOGGER = logging.getLogger(__name__)


class DeviceState:
    """
    Manages the state of an Emotiva device.
    
    This class provides methods for getting and setting device properties,
    with support for listeners that are notified of property changes.
    """
    
    def __init__(self):
        """Initialize the device state."""
        self._properties = {}
        self._property_listeners = {}
        self._lock = asyncio.Lock()
    
    async def set_property(self, name: str, value: Any) -> bool:
        """
        Set a property value and notify listeners if it changed.
        
        Args:
            name: Property name
            value: Property value
            
        Returns:
            bool: True if the property changed, False otherwise
        """
        async with self._lock:
            old_value = self._properties.get(name)
            
            # Don't update if the value hasn't changed
            if old_value == value:
                return False
            
            # Update the property
            self._properties[name] = value
            
            # Log the change
            _LOGGER.debug("Property changed: %s = %s (was %s)", name, value, old_value)
            
            # Notify listeners
            if name in self._property_listeners:
                listeners = list(self._property_listeners[name])
        
        # Call listeners outside the lock to avoid deadlocks
        if name in self._property_listeners:
            for listener in listeners:
                try:
                    result = listener(name, old_value, value)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    _LOGGER.error("Error in property listener: %s", e)
            
        return True
    
    def get_property(self, name: str, default: Any = None) -> Any:
        """
        Get a property value.
        
        Args:
            name: Property name
            default: Default value if property doesn't exist
            
        Returns:
            Property value or default
        """
        return self._properties.get(name, default)
    
    async def get_property_async(self, name: str, default: Any = None) -> Any:
        """
        Get a property value asynchronously (with lock).
        
        Args:
            name: Property name
            default: Default value if property doesn't exist
            
        Returns:
            Property value or default
        """
        async with self._lock:
            return self._properties.get(name, default)
    
    def has_property(self, name: str) -> bool:
        """
        Check if a property exists.
        
        Args:
            name: Property name
            
        Returns:
            bool: True if the property exists
        """
        return name in self._properties
    
    async def delete_property(self, name: str) -> bool:
        """
        Delete a property.
        
        Args:
            name: Property name
            
        Returns:
            bool: True if the property was deleted
        """
        async with self._lock:
            if name in self._properties:
                old_value = self._properties[name]
                del self._properties[name]
                
                # Get listeners
                listeners = []
                if name in self._property_listeners:
                    listeners = list(self._property_listeners[name])
        
        # Notify listeners with None as the new value outside the lock
        for listener in listeners:
            try:
                result = listener(name, old_value, None)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                _LOGGER.error("Error in property listener: %s", e)
            
        return True if listeners else False
    
    def get_properties(self) -> Dict[str, Any]:
        """
        Get all properties.
        
        Returns:
            Dict[str, Any]: All properties
        """
        return self._properties.copy()
    
    async def get_properties_async(self) -> Dict[str, Any]:
        """
        Get all properties asynchronously (with lock).
        
        Returns:
            Dict[str, Any]: All properties
        """
        async with self._lock:
            return self._properties.copy()
    
    async def add_property_listener(
        self, name: str, 
        listener: PropertyCallback
    ) -> None:
        """
        Add a listener for property changes.
        
        Args:
            name: Property name
            listener: Function to call when property changes
        """
        async with self._lock:
            if name not in self._property_listeners:
                self._property_listeners[name] = set()
            
            self._property_listeners[name].add(listener)
    
    async def remove_property_listener(
        self, name: str, 
        listener: PropertyCallback
    ) -> bool:
        """
        Remove a property listener.
        
        Args:
            name: Property name
            listener: Listener to remove
            
        Returns:
            bool: True if the listener was removed
        """
        async with self._lock:
            if name in self._property_listeners and listener in self._property_listeners[name]:
                self._property_listeners[name].remove(listener)
                
                # Clean up empty sets
                if not self._property_listeners[name]:
                    del self._property_listeners[name]
                
                return True
            
            return False
    
    async def clear_property_listeners(self, name: Optional[str] = None) -> None:
        """
        Clear property listeners.
        
        Args:
            name: Property name (None for all properties)
        """
        async with self._lock:
            if name is None:
                self._property_listeners = {}
            elif name in self._property_listeners:
                del self._property_listeners[name]


class PropertyCache:
    """
    Caches property values with TTL expiration.
    
    This class provides a cache for property values that expire after
    a specified time-to-live.
    """
    
    def __init__(self, ttl: float = 60.0):
        """
        Initialize the property cache.
        
        Args:
            ttl: Time-to-live in seconds
        """
        self._cache = {}  # {name: (value, timestamp)}
        self._ttl = ttl
        self._lock = asyncio.Lock()
    
    async def set(self, name: str, value: Any) -> None:
        """
        Set a property value in the cache.
        
        Args:
            name: Property name
            value: Property value
        """
        async with self._lock:
            self._cache[name] = (value, time.time())
    
    async def get(self, name: str, default: Any = None) -> Any:
        """
        Get a property value from the cache, respecting TTL.
        
        Args:
            name: Property name
            default: Default value if property doesn't exist or is expired
            
        Returns:
            Property value or default
        """
        async with self._lock:
            if name in self._cache:
                value, timestamp = self._cache[name]
                
                # Check if expired
                if time.time() - timestamp < self._ttl:
                    return value
                
                # Expired, remove from cache
                del self._cache[name]
            
            return default
    
    async def has(self, name: str) -> bool:
        """
        Check if a property exists in the cache and is not expired.
        
        Args:
            name: Property name
            
        Returns:
            bool: True if the property exists and is not expired
        """
        async with self._lock:
            if name in self._cache:
                _, timestamp = self._cache[name]
                
                # Check if expired
                if time.time() - timestamp < self._ttl:
                    return True
                
                # Expired, remove from cache
                del self._cache[name]
            
            return False
    
    async def delete(self, name: str) -> bool:
        """
        Delete a property from the cache.
        
        Args:
            name: Property name
            
        Returns:
            bool: True if the property was deleted
        """
        async with self._lock:
            if name in self._cache:
                del self._cache[name]
                return True
            
            return False
    
    async def clear(self) -> None:
        """Clear the cache."""
        async with self._lock:
            self._cache = {}
    
    async def set_ttl(self, ttl: float) -> None:
        """
        Set the TTL for the cache.
        
        Args:
            ttl: Time-to-live in seconds
        """
        async with self._lock:
            self._ttl = ttl
    
    async def get_ttl(self) -> float:
        """
        Get the TTL for the cache.
        
        Returns:
            float: Time-to-live in seconds
        """
        async with self._lock:
            return self._ttl


class StateChangeDetector:
    """
    Manages property change watchers.
    
    This class provides methods for registering and removing property watchers,
    which are notified when properties change.
    """
    
    def __init__(self, state: DeviceState):
        """
        Initialize the state change detector.
        
        Args:
            state: Device state to monitor
        """
        self._state = state
        self._watchers = {}
        self._watcher_lock = asyncio.Lock()
    
    async def add_watcher(
        self, property_name: str, 
        callback: PropertyCallback
    ) -> None:
        """
        Add a watcher for a property.
        
        Args:
            property_name: Property to watch
            callback: Function to call when property changes
        """
        async with self._watcher_lock:
            # Create set if it doesn't exist
            if property_name not in self._watchers:
                self._watchers[property_name] = set()
                
                # Register internal listener if this is the first watcher
                await self._state.add_property_listener(
                    property_name, self._property_changed
                )
            
            # Add callback to watchers
            self._watchers[property_name].add(callback)
    
    async def remove_watcher(
        self, property_name: str, 
        callback: PropertyCallback
    ) -> bool:
        """
        Remove a watcher.
        
        Args:
            property_name: Property being watched
            callback: Function to remove
            
        Returns:
            bool: True if the watcher was removed
        """
        async with self._watcher_lock:
            if property_name in self._watchers and callback in self._watchers[property_name]:
                # Remove callback
                self._watchers[property_name].remove(callback)
                
                # If no watchers left, remove internal listener
                if not self._watchers[property_name]:
                    del self._watchers[property_name]
                    await self._state.remove_property_listener(
                        property_name, self._property_changed
                    )
                
                return True
            
            return False
        
    async def _property_changed(self, property_name: str, old_value: Any, new_value: Any) -> None:
        """
        Handle a property change event.
        
        Args:
            property_name: Property that changed
            old_value: Previous value
            new_value: New value
        """
        # Get callbacks (make a copy to avoid modification during iteration)
        callbacks = set()
        async with self._watcher_lock:
            if property_name in self._watchers:
                callbacks = self._watchers[property_name].copy()
        
        # Notify callbacks
        for callback in callbacks:
            try:
                # Check if the callback is a coroutine function
                result = callback(property_name, old_value, new_value)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                _LOGGER.error("Error in state change callback: %s", e)


class MenuStateHandler:
    """
    Handles menu state tracking.
    
    This class provides methods for tracking the current menu state,
    including menu items and position.
    """
    
    def __init__(self, state: DeviceState):
        """
        Initialize the menu state handler.
        
        Args:
            state: Device state object
        """
        self._state = state
        self._menu_id = None
        self._menu_items = []
        self._menu_position = 0
        self._lock = asyncio.Lock()
    
    async def set_current_menu(self, menu_id: str) -> None:
        """
        Set the current menu ID.
        
        Args:
            menu_id: Menu ID
        """
        async with self._lock:
            old_menu_id = self._menu_id
            self._menu_id = menu_id
            
            # Update state
            await self._state.set_property("menu_id", menu_id)
            
            # If menu changed, clear items and position
            if old_menu_id != menu_id:
                self._menu_items = []
                self._menu_position = 0
                await self._state.set_property("menu_items", [])
                await self._state.set_property("menu_position", 0)
    
    def get_current_menu(self) -> Optional[str]:
        """
        Get the current menu ID.
        
        Returns:
            Optional[str]: Current menu ID
        """
        return self._menu_id
    
    async def update_menu_items(self, items: List[Dict[str, Any]]) -> None:
        """
        Update the menu items.
        
        Args:
            items: Menu items
        """
        async with self._lock:
            self._menu_items = items
            
            # Update state
            await self._state.set_property("menu_items", items)
    
    def get_menu_items(self) -> List[Dict[str, Any]]:
        """
        Get the menu items.
        
        Returns:
            List[Dict[str, Any]]: Menu items
        """
        return self._menu_items.copy()
    
    async def set_menu_position(self, position: int) -> None:
        """
        Set the menu position.
        
        Args:
            position: Menu position
        """
        async with self._lock:
            self._menu_position = position
            
            # Update state
            await self._state.set_property("menu_position", position)
    
    def get_menu_position(self) -> int:
        """
        Get the menu position.
        
        Returns:
            int: Menu position
        """
        return self._menu_position
    
    async def clear_menu(self) -> None:
        """Clear the menu state."""
        async with self._lock:
            self._menu_id = None
            self._menu_items = []
            self._menu_position = 0
            
            # Update state
            await self._state.set_property("menu_id", None)
            await self._state.set_property("menu_items", [])
            await self._state.set_property("menu_position", 0)


class BarNotificationHandler:
    """
    Handles bar notification tracking.
    
    This class provides methods for tracking bar notifications and their state.
    """
    
    def __init__(self, state: DeviceState):
        """
        Initialize the bar notification handler.
        
        Args:
            state: Device state object
        """
        self._state = state
        self._bars = {}  # {bar_id: bar_data}
        self._lock = asyncio.Lock()
    
    async def update_bar(
        self, bar_id: int, bar_type: str, text: str,
        value: float = 0.0, min_value: float = 0.0,
        max_value: float = 100.0, units: str = ""
    ) -> None:
        """
        Update a bar notification.
        
        Args:
            bar_id: Bar ID
            bar_type: Bar type
            text: Bar text
            value: Bar value
            min_value: Minimum value
            max_value: Maximum value
            units: Value units
        """
        bar_data = {
            "type": bar_type,
            "text": text,
            "value": value,
            "min_value": min_value,
            "max_value": max_value,
            "units": units
        }
        
        async with self._lock:
            # Check if bar changed
            if (bar_id in self._bars and 
                self._bars[bar_id] == bar_data):
                return
            
            # Update bar
            self._bars[bar_id] = bar_data
            
            # Update state
            await self._state.set_property(f"bar_{bar_id}", bar_data)
            
            # If this is the last bar, update last_bar property
            await self._state.set_property("last_bar", bar_data)
    
    def get_bar(self, bar_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a bar notification.
        
        Args:
            bar_id: Bar ID
            
        Returns:
            Optional[Dict[str, Any]]: Bar data
        """
        return self._bars.get(bar_id)
    
    def get_last_bar_notification(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent bar notification.
        
        Returns:
            Optional[Dict[str, Any]]: Last bar notification
        """
        # Find the highest bar_id
        if not self._bars:
            return None
        
        return self._bars.get(max(self._bars.keys()))
    
    async def clear_bars(self) -> None:
        """Clear all bar notifications."""
        async with self._lock:
            # Get bar IDs
            bar_ids = list(self._bars.keys())
            
            # Clear bars
            self._bars = {}
            
            # Update state
            for bar_id in bar_ids:
                await self._state.delete_property(f"bar_{bar_id}")
            
            await self._state.delete_property("last_bar")


class DeviceConfigState:
    """
    Handles device configuration state.
    
    This class provides methods for tracking device configuration information.
    """
    
    def __init__(self, state: DeviceState):
        """
        Initialize the device configuration state.
        
        Args:
            state: Device state object
        """
        self._state = state
        self._device_info = {}
        self._supported_features = set()
        self._lock = asyncio.Lock()
    
    async def update_device_info(self, device_info: Dict[str, Any]) -> None:
        """
        Update device information.
        
        Args:
            device_info: Device information
        """
        async with self._lock:
            # Update device info
            self._device_info.update(device_info)
            
            # Update state
            for key, value in device_info.items():
                await self._state.set_property(f"device_info_{key}", value)
            
            # Update supported features based on device info
            await self._update_supported_features()
    
    def get_device_info(self) -> Dict[str, Any]:
        """
        Get device information.
        
        Returns:
            Dict[str, Any]: Device information
        """
        return self._device_info.copy()
    
    async def set_supported_feature(self, feature: str, supported: bool = True) -> None:
        """
        Set whether a feature is supported.
        
        Args:
            feature: Feature name
            supported: Whether the feature is supported
        """
        async with self._lock:
            if supported:
                self._supported_features.add(feature)
            elif feature in self._supported_features:
                self._supported_features.remove(feature)
            
            # Update state
            await self._state.set_property(f"supported_feature_{feature}", supported)
    
    def is_feature_supported(self, feature: str) -> bool:
        """
        Check if a feature is supported.
        
        Args:
            feature: Feature name
            
        Returns:
            bool: True if the feature is supported
        """
        return feature in self._supported_features
    
    def get_supported_features(self) -> Set[str]:
        """
        Get all supported features.
        
        Returns:
            Set[str]: Supported features
        """
        return self._supported_features.copy()
    
    async def _update_supported_features(self) -> None:
        """Update supported features based on device info."""
        # Example: supported features based on model
        model = self._device_info.get("model", "").lower()
        
        # Basic features
        basic_features = [
            "power", "volume", "mute", "input"
        ]
        
        # Advanced features
        advanced_features = []
        
        # Model-specific features
        if "xmc" in model:
            advanced_features.extend([
                "zone2", "menu", "audio_mode"
            ])
        
        # Add all features
        for feature in basic_features + advanced_features:
            await self.set_supported_feature(feature, True) 