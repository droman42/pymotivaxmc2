"""
Emotiva Controller Module

This module provides the main controller interface for interacting with Emotiva devices.
It integrates all the modular components (protocol, network, notification, state) into
a cohesive API for controlling and monitoring Emotiva devices.
"""

import logging
import asyncio
import time
from typing import Any, Optional, List, Set, Callable, Union, Tuple, Deque, cast, Dict

from .protocol import CommandFormatter, ResponseParser, EmotivaCommand
from .network import SocketManager, CommandExecutor
from .notifier import (
    ConnectionState, NotificationType,
    NotificationRegistry, NotificationDispatcher, NotificationFilter
)
from .state import (
    DeviceState, PropertyCache, StateChangeDetector,
    MenuStateHandler, BarNotificationHandler, DeviceConfigState
)
from .emotiva_types import (
    EmotivaConfig, BarNotification, BarType,
    EmotivaNotification, PropertyNotification, MenuNotification,
    BarDisplayNotification, EmotivaNotificationListener, NotificationType as EmotivaNotificationType
)
from .constants import (
    DISCOVER_REQ_PORT, DISCOVER_RESP_PORT, NOTIFY_EVENTS,
    PROTOCOL_VERSION, DEFAULT_KEEPALIVE_INTERVAL,
    MODE_PRESETS, INPUT_SOURCES
)
from .exceptions import (
    InvalidTransponderResponseError,
    InvalidSourceError,
    InvalidModeError,
    DeviceOfflineError,
    CommandTimeoutError,
    EmotivaError
)

_LOGGER = logging.getLogger(__name__)


class EmotivaController:
    """
    Main controller class for Emotiva devices.
    
    This class serves as the primary interface for controlling and monitoring Emotiva
    devices. It integrates all the modular components (protocol, network, notification,
    state) into a cohesive API.
    
    Attributes:
        config (EmotivaConfig): Configuration settings for the connection
        device_state (DeviceState): Device state management system
        bar_handler (BarNotificationHandler): Handler for bar notifications
        menu_handler (MenuStateHandler): Handler for menu state
        config_state (DeviceConfigState): Handler for device configuration state
    """
    
    def __init__(self, config: EmotivaConfig):
        """
        Initialize the Emotiva controller.
        
        Args:
            config: Configuration object with device settings
        """
        self.config = config
        
        # Initialize state system
        self.device_state = DeviceState()
        self.bar_handler = BarNotificationHandler(self.device_state)
        self.menu_handler = MenuStateHandler(self.device_state)
        self.config_state = DeviceConfigState(self.device_state)
        self.state_detector = StateChangeDetector(self.device_state)
        
        # Initialize network components
        self.socket_manager = SocketManager()
        self.command_executor = CommandExecutor(self.socket_manager)
        
        # Initialize notification system
        self.notification_registry = NotificationRegistry()
        self.notification_dispatcher = NotificationDispatcher(self.notification_registry)
        
        # Set up initial state
        self._discovery_complete = False
        self._initialized = False
        self._lock = asyncio.Lock()
        self._notification_listener = self._create_notification_listener()
        
        # Keepalive tracking
        self._last_keepalive = time.time()
        self._missed_keepalives = 0
        
        # Initialization
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.initialize())
        except RuntimeError:
            # Not in an asyncio loop, initialization will need to be called manually
            _LOGGER.debug("No asyncio event loop running, initialize() must be called explicitly")
        
        _LOGGER.debug("Initialized EmotivaController with IP: %s", self.config.ip)
    
    def _create_notification_listener(self) -> EmotivaNotificationListener:
        """
        Create a notification listener for handling device notifications.
        
        Returns:
            EmotivaNotificationListener: Instance for handling notifications
        """
        class EmotivaNotificationHandler(EmotivaNotificationListener):
            """Inner class for handling notifications."""
            
            def __init__(self, controller: 'EmotivaController') -> None:
                """Initialize with reference to controller."""
                self.controller = controller
            
            def on_notification(self, notification: EmotivaNotification) -> None:
                """
                Process notifications and update state accordingly.
                
                Args:
                    notification: The notification to process
                """
                # Process based on notification type
                notification_type = notification.notification_type
                
                if notification_type == EmotivaNotificationType.PROPERTY:
                    # Handle property notification
                    self._process_property_notification(notification)
                elif notification_type == EmotivaNotificationType.MENU:
                    # Handle menu notification
                    self._process_menu_notification(notification)
                elif notification_type == EmotivaNotificationType.BAR:
                    # Handle bar notification
                    self._process_bar_notification(notification)
                elif notification_type == EmotivaNotificationType.KEEPALIVE:
                    # Update keepalive timestamp
                    self.controller._last_keepalive = time.time()
                    self.controller._missed_keepalives = 0
                elif notification_type == EmotivaNotificationType.GOODBYE:
                    # Device is shutting down or disconnecting
                    _LOGGER.info("Device %s sent goodbye notification", notification.device_ip)
                
                # Forward notification to registry for observer pattern
                if self.controller.notification_registry:
                    asyncio.create_task(
                        self.controller.notification_registry.notify(notification)
                    )
            
            def _process_property_notification(self, notification: EmotivaNotification) -> None:
                """Process property notification and update state."""
                if isinstance(notification, PropertyNotification) and notification.data:
                    properties = notification.data.get('properties', {})
                    
                    # Update device state with each property
                    for prop_name, prop_data in properties.items():
                        value = prop_data.get('value')
                        if value is not None:
                            asyncio.create_task(
                                self.controller.device_state.set_property(prop_name, value)
                            )
            
            def _process_menu_notification(self, notification: EmotivaNotification) -> None:
                """Process menu notification and update menu state."""
                if isinstance(notification, MenuNotification) and notification.data:
                    menu_data = notification.data
                    
                    # Extract menu data
                    menu_id = menu_data.get('menu_id', '')
                    menu_items = menu_data.get('items', [])
                    menu_position = menu_data.get('position', 0)
                    
                    # Update menu state
                    asyncio.create_task(
                        self.controller.menu_handler.set_current_menu(menu_id)
                    )
                    asyncio.create_task(
                        self.controller.menu_handler.update_menu_items(menu_items)
                    )
                    asyncio.create_task(
                        self.controller.menu_handler.set_menu_position(menu_position)
                    )
            
            def _process_bar_notification(self, notification: EmotivaNotification) -> None:
                """Process bar notification and update bar state."""
                if isinstance(notification, BarDisplayNotification) and notification.data:
                    bar_data = notification.data
                    bars = bar_data.get('bars', [])
                    
                    # Process each bar
                    for i, bar_info in enumerate(bars):
                        bar_type = bar_info.get('type', 'off')
                        text = bar_info.get('text', '')
                        
                        # Extract numeric values for bar type
                        value = 0.0
                        min_value = 0.0
                        max_value = 100.0
                        units = ''
                        
                        if bar_type == 'bar':
                            try:
                                value = float(bar_info.get('value', 0))
                                min_value = float(bar_info.get('min', 0))
                                max_value = float(bar_info.get('max', 100))
                                units = bar_info.get('units', '')
                            except (ValueError, TypeError):
                                pass
                        
                        # Update bar state
                        asyncio.create_task(
                            self.controller.bar_handler.update_bar(
                                bar_id=i,
                                bar_type=bar_type,
                                text=text,
                                value=value,
                                min_value=min_value,
                                max_value=max_value,
                                units=units
                            )
                        )
        
        return EmotivaNotificationHandler(self)
    
    async def initialize(self) -> Dict[str, Any]:
        """
        Initialize the controller and discover device capabilities.
        
        This method performs device discovery, subscribes to notifications,
        and retrieves initial device state.
        
        Returns:
            Dict[str, Any]: Result of the initialization operation
        """
        if self._initialized:
            return {"status": "ok", "message": "Already initialized"}
        
        async with self._lock:
            try:
                # Discover the device
                discovery_result = await self.discover()
                if discovery_result.get("status") != "ok":
                    return discovery_result
                
                # Subscribe to notifications
                subscription_result = await self.subscribe_to_notifications()
                if subscription_result.get("status") != "ok":
                    return subscription_result
                
                # Update device properties
                update_result = await self.update_properties()
                
                # Set initialized flag
                self._initialized = True
                
                # Update device state with initialization status
                await self.device_state.set_property("initialized", True)
                await self.device_state.set_property("connection_state", "online")
                
                _LOGGER.info("EmotivaController initialization complete")
                return {"status": "ok", "message": "Initialization complete"}
                
            except Exception as e:
                _LOGGER.error("Error during initialization: %s", e)
                return {"status": "error", "message": str(e)}
    
    async def discover(self) -> Dict[str, Any]:
        """
        Discover the Emotiva device on the network.
        
        This method sends a discovery packet to the device IP and processes
        the response to determine device capabilities.
        
        Returns:
            Dict[str, Any]: Result of the discovery operation
        """
        if not self.config.ip:
            return {"status": "error", "message": "No IP address configured"}
            
        try:
            # Format the discovery request
            discover_req = CommandFormatter.format_request("discover", {})
            discover_data = discover_req.encode('utf-8')
            
            # Send the request and get response
            _LOGGER.debug("Sending discovery request to %s", self.config.ip)
            response = await self.command_executor.execute_command(
                self.config.ip,
                DISCOVER_REQ_PORT,
                discover_data,
                timeout=self.config.timeout
            )
            
            # Parse the response
            if response is not None:
                parsed_response = ResponseParser.parse_response(response)
                
                if parsed_response and parsed_response.get("status") == "ok":
                    # Extract device information
                    device_info = parsed_response.get("data", {})
                    
                    # Update device state
                    for key, value in device_info.items():
                        await self.device_state.set_property(f"device_{key}", value)
                    
                    # Update config state
                    await self.config_state.update_device_info(device_info)
                    
                    # Extract protocol version and keepalive interval
                    if "protocol" in device_info:
                        await self.device_state.set_property("protocol_version", device_info["protocol"])
                    
                    if "keepaliveInterval" in device_info:
                        try:
                            keepalive_interval = int(device_info["keepaliveInterval"])
                            self.config.keepalive_interval = keepalive_interval
                            await self.device_state.set_property("keepalive_interval", keepalive_interval)
                        except (ValueError, TypeError):
                            pass
                    
                    # Mark discovery as complete
                    self._discovery_complete = True
                    
                    _LOGGER.info("Discovery complete for device at %s", self.config.ip)
                    return {"status": "ok", "data": device_info}
                else:
                    return {"status": "error", "message": "Invalid discovery response"}
            else:
                return {"status": "error", "message": "No response from device"}
                
        except InvalidTransponderResponseError as e:
            _LOGGER.error("Invalid transponder response: %s", e)
            return {"status": "error", "message": str(e)}
        except Exception as e:
            _LOGGER.error("Error during discovery: %s", e)
            return {"status": "error", "message": str(e)}
    
    async def subscribe_to_notifications(
        self, events: Optional[List[str]] = None, auto_update: bool = True
    ) -> Dict[str, Any]:
        """
        Subscribe to device notifications.
        
        Args:
            events: List of event types to subscribe to (None for defaults)
            auto_update: Whether to update properties after subscribing
            
        Returns:
            Dict[str, Any]: Result of the subscription operation
        """
        # Use default subscriptions if none provided
        if events is None:
            events = self.config.default_subscriptions
        
        try:
            # Format the subscription request
            subscribe_req = CommandFormatter.format_request(
                "notifyRequest",
                {"events": events}
            )
            subscribe_data = subscribe_req.encode('utf-8')
            
            # Send the request
            _LOGGER.debug("Subscribing to notifications: %s", events)
            response = await self.command_executor.execute_command(
                self.config.ip,
                DISCOVER_REQ_PORT,
                subscribe_data,
                timeout=self.config.timeout
            )
            
            # Parse the response
            if response is not None:
                parsed_response = ResponseParser.parse_response(response)
                
                if parsed_response and parsed_response.get("status") == "ok":
                    # Update device state with subscribed events
                    await self.device_state.set_property("subscribed_events", events)
                    
                    # Register our notification listener with the registry
                    await self.notification_registry.register_listener(self._notification_listener)
                    
                    # Request current property values
                    if auto_update:
                        await self.update_properties(events)
                    
                    _LOGGER.info("Successfully subscribed to notifications: %s", events)
                    return {"status": "ok", "data": {"subscribed_events": events}}
                else:
                    return {"status": "error", "message": "Failed to subscribe to notifications"}
            else:
                return {"status": "error", "message": "No response from device"}
                
        except Exception as e:
            _LOGGER.error("Error subscribing to notifications: %s", e)
            return {"status": "error", "message": str(e)}
    
    async def update_properties(self, properties: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Request updates for device properties.
        
        Args:
            properties: List of property names to update (None for all subscribed)
            
        Returns:
            Dict[str, Any]: Result of the update operation
        """
        # Use all subscribed events if none provided
        if properties is None:
            subscribed = await self.device_state.get_property("subscribed_events")
            if isinstance(subscribed, list):
                properties = subscribed
            else:
                properties = self.config.default_subscriptions
        
        try:
            # Format the property update request
            update_req = CommandFormatter.format_request(
                "propertyRequest",
                {"properties": properties}
            )
            update_data = update_req.encode('utf-8')
            
            # Send the request
            _LOGGER.debug("Requesting property updates: %s", properties)
            response = await self.command_executor.execute_command(
                self.config.ip,
                DISCOVER_REQ_PORT,
                update_data,
                timeout=self.config.timeout
            )
            
            # Parse the response
            if response is not None:
                parsed_response = ResponseParser.parse_response(response)
                
                if parsed_response and parsed_response.get("status") == "ok":
                    # The actual property values will be updated via notifications
                    _LOGGER.info("Property update request successful")
                    return {"status": "ok", "data": {"requested_properties": properties}}
                else:
                    return {"status": "error", "message": "Failed to update properties"}
            else:
                return {"status": "error", "message": "No response from device"}
                
        except Exception as e:
            _LOGGER.error("Error updating properties: %s", e)
            return {"status": "error", "message": str(e)}
    
    async def send_command(
        self, command: str, params: Optional[Dict[str, Any]] = None, 
        retries: int = 1, timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Send a command to the device.
        
        This is a low-level method for sending arbitrary commands.
        Most use cases should use the specific methods for common operations.
        
        Args:
            command: Command name to send
            params: Command parameters
            retries: Number of retries if command fails
            timeout: Command timeout in seconds (None for default)
            
        Returns:
            Dict[str, Any]: Command result
        """
        if not self.config.ip:
            return {"status": "error", "message": "No IP address configured"}
        
        if timeout is None:
            timeout = self.config.timeout
        
        try:
            # Check connection state
            conn_state = await self.device_state.get_property("connection_state")
            if conn_state == "offline":
                raise DeviceOfflineError(f"Device at {self.config.ip} is offline")
            
            # Format the command
            command_data = CommandFormatter.format_request(command, params)
            command_bytes = command_data.encode('utf-8')
            
            # Send the command with retries
            retry_count = 0
            last_error = None
            
            while retry_count <= retries:
                try:
                    # Send the command
                    _LOGGER.debug("Sending command %s to %s (attempt %d/%d)", 
                                 command, self.config.ip, retry_count + 1, retries + 1)
                    
                    response = await self.command_executor.execute_command(
                        self.config.ip,
                        DISCOVER_REQ_PORT,
                        command_bytes,
                        timeout=timeout
                    )
                    
                    # Parse the response
                    if response is not None:
                        parsed_response = ResponseParser.parse_response(response)
                        # Command successful
                        return parsed_response
                    else:
                        # No response
                        last_error = "No response from device"
                        retry_count += 1
                        
                except CommandTimeoutError as e:
                    # Timeout error
                    last_error = str(e)
                    retry_count += 1
                    
                except Exception as e:
                    # Other error
                    last_error = str(e)
                    retry_count += 1
                
                # Wait before retrying
                if retry_count <= retries:
                    await asyncio.sleep(self.config.retry_delay)
            
            # All retries failed
            _LOGGER.error("Command %s failed after %d attempts: %s", 
                         command, retries + 1, last_error)
            return {"status": "error", "message": last_error or "Command failed"}
            
        except DeviceOfflineError as e:
            _LOGGER.error("Cannot send command to offline device: %s", e)
            return {"status": "error", "message": str(e)}
        except Exception as e:
            _LOGGER.error("Error sending command: %s", e)
            return {"status": "error", "message": str(e)}
    
    async def close(self) -> None:
        """
        Close all connections and release resources.
        
        This method should be called when the controller is no longer needed.
        """
        try:
            # Close network connections
            await self.socket_manager.cleanup()
            
            # Clear notification registrations
            await self.notification_registry.unregister_listener(self._notification_listener)
            
            # Update device state
            await self.device_state.set_property("connection_state", "offline")
            await self.device_state.set_property("initialized", False)
            
            _LOGGER.info("Controller closed and resources released")
        except Exception as e:
            _LOGGER.error("Error closing controller: %s", e)
    
    # Volume control methods
    
    async def get_volume(self) -> Optional[float]:
        """
        Get the current volume level.
        
        Returns:
            Optional[float]: Current volume in dB, or None if unavailable
        """
        # Try to get from the cached state first
        volume = self.device_state.get_property("volume")
        if volume is not None:
            return float(volume)
        
        # If not in cache, request an update
        await self.update_properties(["volume"])
        
        # Wait a moment for notification to arrive
        await asyncio.sleep(0.1)
        
        # Try again
        volume = self.device_state.get_property("volume")
        if volume is not None:
            return float(volume)
        
        return None
    
    async def set_volume(self, volume: float) -> Dict[str, Any]:
        """
        Set the volume level.
        
        Args:
            volume: Volume level in dB
            
        Returns:
            Dict[str, Any]: Command result
        """
        # Format and send control request
        command = CommandFormatter.format_control_request("volume", str(volume))
        result = await self.send_command(command)
        
        # Update local state if successful
        if result.get("status") == "ok":
            await self.device_state.set_property("volume", volume)
        
        return result
    
    async def volume_up(self) -> Dict[str, Any]:
        """
        Increase volume by one step.
        
        Returns:
            Dict[str, Any]: Command result
        """
        command = CommandFormatter.format_control_request("volumeUp", "0")
        return await self.send_command(command)
    
    async def volume_down(self) -> Dict[str, Any]:
        """
        Decrease volume by one step.
        
        Returns:
            Dict[str, Any]: Command result
        """
        command = CommandFormatter.format_control_request("volumeDown", "0")
        return await self.send_command(command)
    
    # Power control methods
    
    async def get_power(self) -> Optional[bool]:
        """
        Get the current power state.
        
        Returns:
            Optional[bool]: True if powered on, False if in standby, None if unavailable
        """
        # Try to get from the cached state first
        power = self.device_state.get_property("power")
        if power is not None:
            return bool(power)
        
        # If not in cache, request an update
        await self.update_properties(["power"])
        
        # Wait a moment for notification to arrive
        await asyncio.sleep(0.1)
        
        # Try again
        power = self.device_state.get_property("power")
        if power is not None:
            return bool(power)
        
        return None
    
    async def power_on(self) -> Dict[str, Any]:
        """
        Power on the device.
        
        Returns:
            Dict[str, Any]: Command result
        """
        command = CommandFormatter.format_control_request("power", "true")
        result = await self.send_command(command)
        
        # Update local state if successful
        if result.get("status") == "ok":
            await self.device_state.set_property("power", True)
        
        return result
    
    async def power_off(self) -> Dict[str, Any]:
        """
        Power off the device (standby).
        
        Returns:
            Dict[str, Any]: Command result
        """
        command = CommandFormatter.format_control_request("power", "false")
        result = await self.send_command(command)
        
        # Update local state if successful
        if result.get("status") == "ok":
            await self.device_state.set_property("power", False)
        
        return result
    
    # Input control methods
    
    async def get_input(self) -> Optional[str]:
        """
        Get the current input source.
        
        Returns:
            Optional[str]: Current input source, or None if unavailable
        """
        # Try to get from the cached state first
        input_source = self.device_state.get_property("input")
        if input_source is not None:
            return str(input_source)
        
        # If not in cache, request an update
        await self.update_properties(["input"])
        
        # Wait a moment for notification to arrive
        await asyncio.sleep(0.1)
        
        # Try again
        input_source = self.device_state.get_property("input")
        if input_source is not None:
            return str(input_source)
        
        return None
    
    async def set_input(self, input_source: str) -> Dict[str, Any]:
        """
        Set the input source.
        
        Args:
            input_source: Input source identifier (e.g., "hdmi1")
            
        Returns:
            Dict[str, Any]: Command result
            
        Raises:
            InvalidSourceError: If the input source is not valid
        """
        # Validate input source
        if input_source not in INPUT_SOURCES:
            raise InvalidSourceError(f"Invalid input source: {input_source}")
        
        # Format and send control request
        command = CommandFormatter.format_control_request("input", input_source)
        result = await self.send_command(command)
        
        # Update local state if successful
        if result.get("status") == "ok":
            await self.device_state.set_property("input", input_source)
        
        return result
    
    # Audio mode methods
    
    async def get_mode(self) -> Optional[str]:
        """
        Get the current audio mode.
        
        Returns:
            Optional[str]: Current audio mode, or None if unavailable
        """
        # Try to get from the cached state first
        mode = self.device_state.get_property("mode")
        if mode is not None:
            return str(mode)
        
        # If not in cache, request an update
        await self.update_properties(["mode"])
        
        # Wait a moment for notification to arrive
        await asyncio.sleep(0.1)
        
        # Try again
        mode = self.device_state.get_property("mode")
        if mode is not None:
            return str(mode)
        
        return None
    
    async def set_mode(self, mode: str) -> Dict[str, Any]:
        """
        Set the audio mode.
        
        Args:
            mode: Audio mode identifier (e.g., "movie", "music")
            
        Returns:
            Dict[str, Any]: Command result
            
        Raises:
            InvalidModeError: If the audio mode is not valid
        """
        # Validate audio mode
        if mode not in MODE_PRESETS:
            raise InvalidModeError(f"Invalid audio mode: {mode}")
        
        # Format and send control request
        command = CommandFormatter.format_control_request("mode", mode)
        result = await self.send_command(command)
        
        # Update local state if successful
        if result.get("status") == "ok":
            await self.device_state.set_property("mode", mode)
        
        return result
    
    # Device information methods
    
    async def get_device_info(self) -> Dict[str, Any]:
        """
        Get device information.
        
        Returns:
            Dict[str, Any]: Device information
        """
        # Try to get from the config state first
        device_info = self.config_state.get_device_info()
        if device_info:
            return device_info
        
        # If not available, try discovery again
        await self.discover()
        
        # Return updated info
        return self.config_state.get_device_info() or {}
    
    # State access methods
    
    def get_state(self) -> DeviceState:
        """
        Get the device state object.
        
        Returns:
            DeviceState: Device state object
        """
        return self.device_state
    
    def get_bar_handler(self) -> BarNotificationHandler:
        """
        Get the bar notification handler.
        
        Returns:
            BarNotificationHandler: Bar notification handler
        """
        return self.bar_handler
    
    def get_menu_handler(self) -> MenuStateHandler:
        """
        Get the menu state handler.
        
        Returns:
            MenuStateHandler: Menu state handler
        """
        return self.menu_handler
    
    def get_config_state(self) -> DeviceConfigState:
        """
        Get the device configuration state.
        
        Returns:
            DeviceConfigState: Device configuration state
        """
        return self.config_state
    
    # Connection state methods
    
    def is_connected(self) -> bool:
        """
        Check if the device is connected.
        
        Returns:
            bool: True if connected, False otherwise
        """
        conn_state = self.device_state.get_property("connection_state")
        return conn_state == "online"
    
    def get_connection_state(self) -> str:
        """
        Get the connection state as a string.
        
        Returns:
            str: Connection state ("online", "offline", or "unknown")
        """
        conn_state = self.device_state.get_property("connection_state")
        return str(conn_state) if conn_state else "unknown"
    
    async def register_connection_callback(
        self, callback: Callable[[str, str], None]
    ) -> None:
        """
        Register a callback for connection state changes.
        
        Args:
            callback: Function to call when connection state changes
        """
        # Create a state watcher for connection state changes
        await self.state_detector.add_watcher("connection_state", 
            lambda prop_name, old_val, new_val: callback(old_val, new_val)
        )
    
    async def unregister_connection_callback(
        self, callback: Callable[[str, str], None]
    ) -> None:
        """
        Unregister a connection state callback.
        
        Args:
            callback: The callback to unregister
        """
        # Find existing watcher
        for watcher in self.state_detector._watchers.get("connection_state", []):
            if watcher.__name__ == callback.__name__:
                await self.state_detector.remove_watcher("connection_state", watcher)
                break
    
    # Notification registration methods
    
    async def register_property_callback(
        self, property_name: str, callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Register a callback for property changes.
        
        Args:
            property_name: Name of the property to watch
            callback: Function to call when property changes
        """
        # Create a state watcher for the property
        await self.state_detector.add_watcher(property_name, 
            lambda prop_name, old_val, new_val: callback({"name": prop_name, "old": old_val, "new": new_val})
        )
    
    async def unregister_property_callback(
        self, property_name: str, callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Unregister a property callback.
        
        Args:
            property_name: Name of the property
            callback: The callback to unregister
        """
        # Find existing watcher
        for watcher in self.state_detector._watchers.get(property_name, []):
            if watcher.__name__ == callback.__name__:
                await self.state_detector.remove_watcher(property_name, watcher)
                break
    
    # Menu control methods
    
    async def send_menu_command(self, command: str) -> Dict[str, Any]:
        """
        Send a menu control command.
        
        Args:
            command: Menu command ("up", "down", "left", "right", "select", "back", "home")
            
        Returns:
            Dict[str, Any]: Command result
        """
        # Validate menu command
        valid_commands = ["up", "down", "left", "right", "select", "back", "home"]
        if command not in valid_commands:
            return {"status": "error", "message": f"Invalid menu command: {command}"}
        
        # Format and send control request
        cmd_request = CommandFormatter.format_control_request(f"menu_{command}", "0")
        return await self.send_command(cmd_request)
    
    async def get_last_menu_notification(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent menu notification.
        
        Returns:
            Optional[Dict[str, Any]]: Menu notification data, or None if not available
        """
        # Construct menu data from menu handler state
        menu_id = self.menu_handler.get_current_menu()
        menu_items = self.menu_handler.get_menu_items()
        menu_position = self.menu_handler.get_menu_position()
        
        if menu_id is not None:
            return {
                "menu_id": menu_id,
                "items": menu_items,
                "position": menu_position
            }
        
        return None
    
    # Zone2 control methods
    
    async def set_zone2_volume(self, volume: float) -> Dict[str, Any]:
        """
        Set Zone2 volume level.
        
        Args:
            volume: Volume level in dB
            
        Returns:
            Dict[str, Any]: Command result
        """
        # Format and send control request
        command = CommandFormatter.format_control_request("zone2_volume", str(volume))
        result = await self.send_command(command)
        
        # Update local state if successful
        if result.get("status") == "ok":
            await self.device_state.set_property("zone2_volume", volume)
        
        return result
    
    async def set_zone2_power(self, power: bool) -> Dict[str, Any]:
        """
        Set Zone2 power state.
        
        Args:
            power: True to power on, False to power off
            
        Returns:
            Dict[str, Any]: Command result
        """
        power_value = "true" if power else "false"
        command = CommandFormatter.format_control_request("zone2_power", power_value)
        result = await self.send_command(command)
        
        # Update local state if successful
        if result.get("status") == "ok":
            await self.device_state.set_property("zone2_power", power)
        
        return result
    
    async def set_zone2_input(self, input_source: str) -> Dict[str, Any]:
        """
        Set Zone2 input source.
        
        Args:
            input_source: Input source identifier (e.g., "hdmi1")
            
        Returns:
            Dict[str, Any]: Command result
            
        Raises:
            InvalidSourceError: If the input source is not valid
        """
        # Validate input source
        if input_source not in INPUT_SOURCES:
            raise InvalidSourceError(f"Invalid input source: {input_source}")
        
        # Format and send control request
        command = CommandFormatter.format_control_request("zone2_input", input_source)
        result = await self.send_command(command)
        
        # Update local state if successful
        if result.get("status") == "ok":
            await self.device_state.set_property("zone2_input", input_source)
        
        return result
    
    async def get_zone2_state(self) -> Dict[str, Any]:
        """
        Get Zone2 state information.
        
        Returns:
            Dict[str, Any]: Zone2 state information
        """
        # Get zone2 properties from device state
        zone2_power = self.device_state.get_property("zone2_power")
        zone2_volume = self.device_state.get_property("zone2_volume")
        zone2_input = self.device_state.get_property("zone2_input")
        
        # If any property is missing, request an update
        if zone2_power is None or zone2_volume is None or zone2_input is None:
            await self.update_properties(["zone2_power", "zone2_volume", "zone2_input"])
            
            # Wait a moment for notifications to arrive
            await asyncio.sleep(0.1)
            
            # Try again
            zone2_power = self.device_state.get_property("zone2_power")
            zone2_volume = self.device_state.get_property("zone2_volume")
            zone2_input = self.device_state.get_property("zone2_input")
        
        return {
            "status": "ok",
            "data": {
                "power": "true" if zone2_power else "false",
                "volume": str(zone2_volume) if zone2_volume is not None else "0",
                "input": zone2_input if zone2_input is not None else "unknown"
            }
        } 