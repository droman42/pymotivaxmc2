"""Dispatches notifications to interested callbacks."""
from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from typing import Callable, Awaitable, Dict, Coroutine, Any

from .logging import get_logger
from .xmlcodec import parse_xml

# Module logger
_LOGGER = get_logger("dispatcher")

Callback = Callable[[Any], Awaitable[None]] | Callable[[Any], None]

class Dispatcher:
    def __init__(self, socket_mgr, notify_port_name: str):
        self.socket_mgr = socket_mgr
        self.notify_port_name = notify_port_name
        self._listeners: Dict[str, list[Callback]] = defaultdict(list)
        self._task: asyncio.Task | None = None
        
        # Phase 1 Fix: Add callback timeout protection and task management
        self._active_tasks: set[asyncio.Task] = set()
        self._callback_timeout = 5.0  # 5 second timeout for callbacks
        
        _LOGGER.debug("Dispatcher initialized for port %s", notify_port_name)

    def on(self, prop: str, cb: Callback):
        self._listeners[prop].append(cb)
        _LOGGER.debug("Registered callback for property '%s'", prop)

    async def start(self):
        _LOGGER.info("Starting notification dispatcher")
        if self._task and not self._task.done():
            _LOGGER.warning("Dispatcher already running, stopping previous instance")
            await self.stop()
            
        self._task = asyncio.create_task(self._run())
        _LOGGER.debug("Dispatcher started")

    async def stop(self):
        _LOGGER.info("Stopping notification dispatcher")
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            _LOGGER.debug("Dispatcher stopped")
            
        # Phase 1 Fix: Cancel all active callback tasks during shutdown
        if self._active_tasks:
            _LOGGER.debug("Cancelling %d active callback tasks", len(self._active_tasks))
            for task in self._active_tasks:
                task.cancel()
            # Wait for tasks to complete cancellation
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
            self._active_tasks.clear()

    def _remove_task(self, task: asyncio.Task):
        """Remove completed task from active set."""
        self._active_tasks.discard(task)

    def _extract_properties(self, xml):
        """Extract properties from notification XML, handling both protocol formats.
        
        Returns:
            dict: Property name -> value mappings extracted from the XML
        """
        properties = {}
        
        # Check for Protocol 3.0+ format first (property elements with name attributes)
        property_elements = xml.findall("property")
        if property_elements:
            # Protocol 3.0+ format: <property name="volume" value="-20.5" visible="true"/>
            for prop_elem in property_elements:
                prop_name = prop_elem.get("name")
                if prop_name:
                    # Prefer 'value' attribute, fall back to text content
                    value = prop_elem.get("value", "") or prop_elem.text or ""
                    properties[prop_name] = value
                    _LOGGER.debug("Extracted property '%s' = '%s' (Protocol 3.0+ format)", 
                                prop_name, value)
        else:
            # Protocol 2.0 format: direct child elements like <volume>-20.5</volume>
            for prop_elem in xml:
                prop_name = prop_elem.tag
                # Prefer text content, fall back to 'value' attribute
                value = prop_elem.text or prop_elem.get("value", "")
                properties[prop_name] = value
                _LOGGER.debug("Extracted property '%s' = '%s' (Protocol 2.0 format)",
                            prop_name, value)
        
        return properties

    async def _dispatch_property(self, prop_name: str, value: str):
        """Dispatch a single property notification to its listeners."""
        listeners = self._listeners.get(prop_name, [])
        if listeners:
            _LOGGER.debug("Dispatching property '%s' to %d listeners", prop_name, len(listeners))
            
            # Phase 1 Fix: Protected callback execution with timeout and task management
            for cb in listeners:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        # Wrap callback with timeout protection
                        callback_coro = asyncio.wait_for(cb(value), timeout=self._callback_timeout)
                        task = asyncio.create_task(callback_coro)
                        
                        # Add to active tasks and set up cleanup
                        self._active_tasks.add(task)
                        task.add_done_callback(self._remove_task)
                        
                    else:
                        # Phase 1 Fix: Run synchronous callbacks in thread pool to avoid blocking
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(None, cb, value)
                        
                except asyncio.TimeoutError:
                    _LOGGER.warning("Callback timeout for property '%s' after %.1f seconds", 
                                  prop_name, self._callback_timeout)
                except Exception as e:
                    _LOGGER.error("Error in callback for '%s': %s", prop_name, e)
        else:
            _LOGGER.debug("No listeners for property '%s'", prop_name)

    async def _run(self):
        _LOGGER.debug("Dispatcher listening on port %s", self.notify_port_name)
        while True:
            try:
                data, _ = await self.socket_mgr.recv(self.notify_port_name)
                xml = parse_xml(data)
                
                if xml.tag == "emotivaNotify":
                    # Extract sequence number for logging (optional)
                    sequence = xml.get("sequence")
                    if sequence:
                        _LOGGER.debug("Processing notification sequence %s", sequence)
                    
                    # Extract all properties from the notification using dual-format logic
                    properties = self._extract_properties(xml)
                    
                    if properties:
                        _LOGGER.debug("Received notification with %d properties: %s", 
                                    len(properties), list(properties.keys()))
                        
                        # Dispatch each property to its listeners
                        for prop_name, value in properties.items():
                            await self._dispatch_property(prop_name, value)
                    else:
                        _LOGGER.warning("Received emotivaNotify with no extractable properties")
                        
                elif xml.tag == "emotivaMenuNotify":
                    # Handle menu notifications (future enhancement)
                    _LOGGER.debug("Received menu notification (not implemented)")
                    
                elif xml.tag == "emotivaBarNotify":
                    # Handle bar notifications (future enhancement) 
                    _LOGGER.debug("Received bar notification (not implemented)")
                    
                else:
                    _LOGGER.warning("Unexpected message type on notify port: %s", xml.tag)
                    
            except asyncio.CancelledError:
                _LOGGER.debug("Dispatcher task cancelled")
                raise
            except Exception as e:
                _LOGGER.error("Error in notification dispatcher: %s", e)
