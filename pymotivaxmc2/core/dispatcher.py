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

    async def _run(self):
        _LOGGER.debug("Dispatcher listening on port %s", self.notify_port_name)
        while True:
            try:
                data, _ = await self.socket_mgr.recv(self.notify_port_name)
                xml = parse_xml(data)
                
                if xml.tag == "emotivaNotify":
                    prop = xml.get("name")
                    value = xml.text
                    
                    if prop:
                        _LOGGER.debug("Received notification: %s = %s", prop, value)
                        listeners = self._listeners.get(prop, [])
                        if listeners:
                            _LOGGER.debug("Dispatching to %d listeners", len(listeners))
                            
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
                                                  prop, self._callback_timeout)
                                except Exception as e:
                                    _LOGGER.error("Error in callback for '%s': %s", prop, e)
                        else:
                            _LOGGER.debug("No listeners for property '%s'", prop)
                    else:
                        _LOGGER.warning("Received notification without property name")
                else:
                    _LOGGER.warning("Unexpected message type on notify port: %s", xml.tag)
            except asyncio.CancelledError:
                _LOGGER.debug("Dispatcher task cancelled")
                raise
            except Exception as e:
                _LOGGER.error("Error in notification dispatcher: %s", e)
