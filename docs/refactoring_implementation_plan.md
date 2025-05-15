# Emotiva Integration Architecture: Refactoring Implementation Plan

## Overview

This document outlines the detailed implementation plan for refactoring the Emotiva integration architecture into well-defined modules with clear responsibilities. The refactoring will be executed in five phases, each focusing on a specific layer of the architecture.

## Phase 1: Extract Protocol Layer

**Goal**: Create a dedicated module to handle all protocol-specific operations.

### Tasks:

1. **Create `protocol.py` module**
   - Implement `CommandFormatter` class for XML generation
   - Implement `ResponseParser` class for XML parsing
   - Create `ProtocolVersion` for version compatibility handling

2. **Move XML formatting logic from `emotiva.py`**
   - Extract `format_request()` to `CommandFormatter.format_request()`
   - Extract response parsing logic to `ResponseParser.parse_response()`
   - Create specialized parsers for different response types (command, notify, transponder)

3. **Define clear interfaces**
   - Create `EmotivaCommand` class to represent commands
   - Create `EmotivaResponse` class hierarchy for different response types
   - Define protocol constants in a separate namespace

4. **Implementation details**:
   ```python
   # CommandFormatter example
   class CommandFormatter:
       @staticmethod
       def format_request(command_type, params=None, protocol_version=None):
           """Format a request as XML according to the Emotiva protocol."""
           # XML formatting logic here
           
       @staticmethod
       def format_control_request(command, value, ack=False):
           """Format a control request."""
           # Control command formatting
   
   # ResponseParser example
   class ResponseParser:
       @staticmethod
       def parse_response(response_xml, response_type=None):
           """Parse an XML response into a structured object."""
           # XML parsing logic
   ```

5. **Add tests**
   - Test XML formatting for various command types
   - Test parsing responses from sample XML
   - Test version compatibility handling

## Phase 2: Enhance Network Layer

**Goal**: Refactor network-related code into a dedicated module with clear responsibilities.

### Tasks:

1. **Refactor `network.py`**
   - Implement `SocketManager` for socket lifecycle management
   - Create `EmotivaNetworkDiscovery` for device discovery
   - Implement `BroadcastListener` for handling device announcements

2. **Move socket management from `emotiva.py`**
   - Extract socket creation and connection logic
   - Move UDP packet sending/receiving logic
   - Extract broadcast handling code

3. **Implement connection monitoring**
   - Create `ConnectionManager` to track connection health
   - Implement timeout handling and reconnection logic
   - Add connection state tracking and notifications

4. **Implementation details**:
   ```python
   # SocketManager example
   class SocketManager:
       def __init__(self, timeout=2.0):
           self.timeout = timeout
           self._sockets = {}
       
       async def get_socket(self, host, port, socket_type='udp'):
           """Get or create a socket for the specified host/port."""
           # Socket management logic
       
       async def send_packet(self, host, port, data, socket_type='udp'):
           """Send a packet to the specified host/port."""
           # Packet sending logic
   
   # EmotivaNetworkDiscovery example
   class EmotivaNetworkDiscovery:
       def __init__(self, socket_manager, protocol_formatter):
           self.socket_manager = socket_manager
           self.protocol_formatter = protocol_formatter
       
       async def discover_devices(self, broadcast_addr='255.255.255.255', 
                                 port=7000, timeout=5.0):
           """Discover Emotiva devices on the network."""
           # Discovery logic
   ```

5. **Add tests**
   - Test socket creation and management
   - Test packet sending and receiving
   - Test device discovery with mock responses

## Phase 3: Extend Notification Layer

**Goal**: Enhance notification handling with proper observer pattern implementation.

### Tasks:

1. **Refactor `notifier.py`**
   - Implement `NotificationRegistry` to manage subscriptions
   - Create `NotificationDispatcher` to route notifications to callbacks
   - Implement specialized notification parsers

2. **Move notification handling from `emotiva.py`**
   - Extract event callback registration logic
   - Move notification processing code
   - Extract subscription management logic

3. **Implement Observer pattern**
   - Create `NotificationListener` interface
   - Implement different notification type handlers
   - Add support for filtering notifications

4. **Implement specialized notification types**
   - Add support for bar notifications
   - Add support for menu notifications
   - Add support for keepalive notifications

5. **Implementation details**:
   ```python
   # NotificationRegistry example
   class NotificationRegistry:
       def __init__(self):
           self._subscriptions = {}
           self._listeners = set()
       
       def register_listener(self, listener):
           """Register a notification listener."""
           self._listeners.add(listener)
       
       def unregister_listener(self, listener):
           """Unregister a notification listener."""
           if listener in self._listeners:
               self._listeners.remove(listener)
   
   # NotificationDispatcher example
   class NotificationDispatcher:
       def __init__(self, registry):
           self.registry = registry
       
       async def dispatch_notification(self, notification):
           """Dispatch a notification to registered listeners."""
           # Notification dispatching logic
   ```

6. **Add tests**
   - Test notification registration and dispatching
   - Test parsing different notification types
   - Test observer pattern implementation

## Phase 4: Implement State Management

**Goal**: Create a dedicated module for tracking device state.

### Tasks:

1. **Create `state.py` module**
   - Implement `DeviceState` class for state tracking
   - Create `PropertyCache` for caching device properties
   - Implement `StateChangeDetector` for detecting state changes

2. **Move state tracking from `emotiva.py`**
   - Extract property storage logic
   - Move state change detection code
   - Extract notification history tracking

3. **Implement property change notifications**
   - Add property change event system
   - Implement dirty checking for properties
   - Add support for property validation

4. **Implement specialized state handlers**
   - Add support for bar notification state
   - Add support for menu state
   - Add support for device configuration state

5. **Implementation details**:
   ```python
   # DeviceState example
   class DeviceState:
       def __init__(self):
           self._properties = {}
           self._listeners = set()
           self._lock = asyncio.Lock()
       
       async def set_property(self, name, value):
           """Set a property value and notify listeners of changes."""
           async with self._lock:
               old_value = self._properties.get(name)
               if old_value != value:
                   self._properties[name] = value
                   await self._notify_property_change(name, old_value, value)
       
       def get_property(self, name, default=None):
           """Get a property value."""
           return self._properties.get(name, default)
   
   # PropertyCache example
   class PropertyCache:
       def __init__(self, ttl=300):  # 5 minutes default TTL
           self._cache = {}
           self._ttl = ttl
       
       def set(self, key, value):
           """Set a value in the cache with timestamp."""
           self._cache[key] = (value, time.time())
       
       def get(self, key, default=None):
           """Get a value from the cache, respecting TTL."""
           if key in self._cache:
               value, timestamp = self._cache[key]
               if time.time() - timestamp < self._ttl:
                   return value
               del self._cache[key]
           return default
   ```

6. **Add tests**
   - Test property setting and getting
   - Test state change detection
   - Test property cache with TTL

## Phase 5: Refactor Controller Layer

**Goal**: Simplify the main controller class to use the new components.

### Tasks:

1. **Refactor `emotiva.py`**
   - Implement `EmotivaController` as main facade class
   - Create `CommandExecutor` for command execution with error handling
   - Simplify public API methods

2. **Integrate with new components**
   - Update to use Protocol layer for command formatting
   - Update to use Network layer for communication
   - Update to use Notification layer for events
   - Update to use State layer for property tracking

3. **Improve error handling**
   - Add consistent error handling across methods
   - Implement retry logic for network operations
   - Add proper logging throughout the system

4. **Optimize public API**
   - Create consistent method naming
   - Add proper documentation for all methods

5. **Implementation details**:
   ```python
   # EmotivaController example
   class EmotivaController:
       def __init__(self, config=None):
           self.config = config or EmotivaConfig()
           self.protocol = CommandFormatter()
           self.network = SocketManager()
           self.discovery = EmotivaNetworkDiscovery(self.network, self.protocol)
           self.state = DeviceState()
           self.notifier = NotificationRegistry()
           self.command_executor = CommandExecutor(self.network, self.protocol)
       
       async def connect(self, host=None, port=None):
           """Connect to an Emotiva device."""
           # Connection logic using the network layer
       
       async def set_volume(self, volume, zone=1):
           """Set the volume for the specified zone."""
           # Command execution using the command executor
   
   # CommandExecutor example
   class CommandExecutor:
       def __init__(self, network, protocol):
           self.network = network
           self.protocol = protocol
       
       async def execute_command(self, device, command, value=0, ack=False, 
                               retries=3, timeout=2.0):
           """Execute a command on the device with retries."""
           # Command execution logic
   ```

6. **Add tests**
   - Test controller initialization and connection
   - Test command execution with mock network
   - Test integration with all layers

## Integration and Testing

After completing each phase, integration testing will be performed to ensure that the refactored components work correctly together. The integration testing will include:

1. **Functional testing**
   - Test end-to-end scenarios with real devices
   - Test error handling and recovery
   - Test performance and resource usage

2. **Regression testing**
   - Ensure existing functionality is preserved
   - Verify that all device types still work
   - Check that all notification types are handled correctly

3. **Documentation**
   - Update API documentation
   - Create architecture diagrams
   - Update usage examples

## Timeline and Dependencies

| Phase | Estimated Duration | Dependencies |
|-------|-------------------|--------------|
| Phase 1: Protocol Layer | 1-2 weeks | None |
| Phase 2: Network Layer | 1-2 weeks | Phase 1 |
| Phase 3: Notification Layer | 2-3 weeks | Phase 1, Phase 2 |
| Phase 4: State Management | 1-2 weeks | Phase 1 |
| Phase 5: Controller Layer | 2-3 weeks | Phase 1-4 |
| Integration and Testing | 1-2 weeks | Phase 1-5 |

Total estimated time: 8-14 weeks

## Risk Management

1. **Integration issues between components**
   - Mitigation: Define clear interfaces and test integration early
   - Fallback: Implement temporary adapters for problem areas

2. **Performance regression**
   - Mitigation: Benchmark key operations before and after refactoring
   - Fallback: Optimize critical paths if performance degrades

3. **Unforeseen device behavior**
   - Mitigation: Test with multiple device types and firmware versions
   - Fallback: Add device-specific handling where necessary

## Conclusion

This refactoring plan provides a structured approach to improving the architecture of the Emotiva integration. By breaking the work into focused phases and defining clear responsibilities for each component, we can create a more maintainable, testable, and extensible system.

The refactored architecture will make it easier to:
- Add support for new device types
- Handle protocol changes in future firmware
- Extend the system with new features
- Test components in isolation
- Fix bugs without introducing regressions 