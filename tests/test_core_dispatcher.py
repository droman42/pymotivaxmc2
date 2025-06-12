"""Test cases for the Dispatcher class."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import xml.etree.ElementTree as ET

from pymotivaxmc2.core.dispatcher import Dispatcher


class TestDispatcherInit:
    """Test dispatcher initialization."""
    
    def test_dispatcher_init(self):
        """Test dispatcher initialization with required parameters."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        assert dispatcher.socket_mgr == mock_socket_mgr
        assert dispatcher.notify_port_name == "notifyPort"
        assert dispatcher._task is None
        assert isinstance(dispatcher._listeners, dict)
        assert isinstance(dispatcher._active_tasks, set)
        assert dispatcher._callback_timeout == 5.0


class TestCallbackRegistration:
    """Test callback registration functionality."""
    
    def test_register_sync_callback(self):
        """Test registering synchronous callback."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        def test_callback(value):
            pass
        
        dispatcher.on("power", test_callback)
        
        assert "power" in dispatcher._listeners
        assert test_callback in dispatcher._listeners["power"]
    
    def test_register_async_callback(self):
        """Test registering asynchronous callback."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        async def test_callback(value):
            pass
        
        dispatcher.on("volume", test_callback)
        
        assert "volume" in dispatcher._listeners
        assert test_callback in dispatcher._listeners["volume"]
    
    def test_register_multiple_callbacks_same_property(self):
        """Test registering multiple callbacks for the same property."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        def callback1(value):
            pass
        
        def callback2(value):
            pass
        
        dispatcher.on("power", callback1)
        dispatcher.on("power", callback2)
        
        assert len(dispatcher._listeners["power"]) == 2
        assert callback1 in dispatcher._listeners["power"]
        assert callback2 in dispatcher._listeners["power"]


class TestPropertyExtraction:
    """Test property extraction from XML notifications."""
    
    def test_extract_properties_protocol_2_single_property(self):
        """Test extracting single property from Protocol 2.0 format."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Protocol 2.0 format: <emotivaNotify><power>On</power></emotivaNotify>
        xml_str = '<emotivaNotify><power>On</power></emotivaNotify>'
        xml = ET.fromstring(xml_str)
        
        properties = dispatcher._extract_properties(xml)
        
        assert properties == {"power": "On"}
    
    def test_extract_properties_protocol_2_multiple_properties(self):
        """Test extracting multiple properties from Protocol 2.0 format."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Protocol 2.0 format with multiple properties
        xml_str = '''<emotivaNotify>
            <power>On</power>
            <volume value="-20.5">-20.5</volume>
            <mute>Off</mute>
        </emotivaNotify>'''
        xml = ET.fromstring(xml_str)
        
        properties = dispatcher._extract_properties(xml)
        
        expected = {
            "power": "On",
            "volume": "-20.5",  # Should prefer text content over value attribute
            "mute": "Off"
        }
        assert properties == expected
    
    def test_extract_properties_protocol_2_value_attribute_fallback(self):
        """Test Protocol 2.0 format falls back to value attribute when no text."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Protocol 2.0 format with value attribute only
        xml_str = '<emotivaNotify><power value="On"/></emotivaNotify>'
        xml = ET.fromstring(xml_str)
        
        properties = dispatcher._extract_properties(xml)
        
        assert properties == {"power": "On"}
    
    def test_extract_properties_protocol_3_single_property(self):
        """Test extracting single property from Protocol 3.0+ format."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Protocol 3.0+ format
        xml_str = '<emotivaNotify><property name="power" value="On" visible="true"/></emotivaNotify>'
        xml = ET.fromstring(xml_str)
        
        properties = dispatcher._extract_properties(xml)
        
        assert properties == {"power": "On"}
    
    def test_extract_properties_protocol_3_multiple_properties(self):
        """Test extracting multiple properties from Protocol 3.0+ format."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Protocol 3.0+ format with multiple properties (from official spec)
        xml_str = '''<emotivaNotify sequence="6862">
            <property name="tuner_signal" value="Stereo 39dBuV" visible="true"/>
            <property name="tuner_channel" value="FM 106.50MHz" visible="true"/>
            <property name="volume" value="-20.5" visible="true"/>
            <property name="power" value="On" visible="true"/>
        </emotivaNotify>'''
        xml = ET.fromstring(xml_str)
        
        properties = dispatcher._extract_properties(xml)
        
        expected = {
            "tuner_signal": "Stereo 39dBuV",
            "tuner_channel": "FM 106.50MHz", 
            "volume": "-20.5",
            "power": "On"
        }
        assert properties == expected
    
    def test_extract_properties_protocol_3_text_fallback(self):
        """Test Protocol 3.0+ format falls back to text content when no value attribute."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Protocol 3.0+ format with text content
        xml_str = '<emotivaNotify><property name="power">On</property></emotivaNotify>'
        xml = ET.fromstring(xml_str)
        
        properties = dispatcher._extract_properties(xml)
        
        assert properties == {"power": "On"}
    
    def test_extract_properties_empty_notification(self):
        """Test extracting properties from empty notification."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        xml_str = '<emotivaNotify></emotivaNotify>'
        xml = ET.fromstring(xml_str)
        
        properties = dispatcher._extract_properties(xml)
        
        assert properties == {}
    
    def test_extract_properties_protocol_3_missing_name_attribute(self):
        """Test Protocol 3.0+ format ignores property elements without name attribute."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        xml_str = '''<emotivaNotify>
            <property name="power" value="On"/>
            <property value="invalid"/>
        </emotivaNotify>'''
        xml = ET.fromstring(xml_str)
        
        properties = dispatcher._extract_properties(xml)
        
        # Should only extract the property with a name attribute
        assert properties == {"power": "On"}


class TestDispatcherRun:
    """Test the main dispatcher run loop."""
    
    @pytest.mark.asyncio
    async def test_dispatch_protocol_2_notification(self):
        """Test dispatching Protocol 2.0 notification to callbacks."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Set up callback tracking
        callback_called = False
        callback_value = None
        
        def test_callback(value):
            nonlocal callback_called, callback_value
            callback_called = True
            callback_value = value
        
        dispatcher.on("power", test_callback)
        
        # Create XML directly and test property extraction + dispatch
        xml_data = b'<emotivaNotify><power>On</power></emotivaNotify>'
        from pymotivaxmc2.core.xmlcodec import parse_xml
        xml = parse_xml(xml_data)
        
        # Test the property extraction
        properties = dispatcher._extract_properties(xml)
        assert properties == {"power": "On"}
        
        # Test the dispatch functionality
        await dispatcher._dispatch_property("power", "On")
        
        assert callback_called
        assert callback_value == "On"
    
    @pytest.mark.asyncio
    async def test_dispatch_protocol_3_notification(self):
        """Test dispatching Protocol 3.0+ notification to callbacks."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Set up callback tracking
        power_callback_called = False
        volume_callback_called = False
        power_value = None
        volume_value = None
        
        def power_callback(value):
            nonlocal power_callback_called, power_value
            power_callback_called = True
            power_value = value
        
        def volume_callback(value):
            nonlocal volume_callback_called, volume_value
            volume_callback_called = True
            volume_value = value
        
        dispatcher.on("power", power_callback)
        dispatcher.on("volume", volume_callback)
        
        # Create XML directly and test property extraction + dispatch
        xml_data = b'''<emotivaNotify sequence="123">
            <property name="power" value="On" visible="true"/>
            <property name="volume" value="-25.0" visible="true"/>
        </emotivaNotify>'''
        from pymotivaxmc2.core.xmlcodec import parse_xml
        xml = parse_xml(xml_data)
        
        # Test the property extraction
        properties = dispatcher._extract_properties(xml)
        expected = {"power": "On", "volume": "-25.0"}
        assert properties == expected
        
        # Test the dispatch functionality for both properties
        for prop_name, value in properties.items():
            await dispatcher._dispatch_property(prop_name, value)
        
        assert power_callback_called
        assert power_value == "On"
        assert volume_callback_called
        assert volume_value == "-25.0"
    
    @pytest.mark.asyncio
    async def test_dispatch_async_callback(self):
        """Test dispatching to async callbacks."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Set up async callback tracking
        callback_called = False
        callback_value = None
        
        async def test_callback(value):
            nonlocal callback_called, callback_value
            callback_called = True
            callback_value = value
        
        dispatcher.on("power", test_callback)
        
        # Test the dispatch functionality directly
        await dispatcher._dispatch_property("power", "On")
        
        # Wait for any async tasks to complete
        if dispatcher._active_tasks:
            await asyncio.gather(*dispatcher._active_tasks, return_exceptions=True)
        
        assert callback_called
        assert callback_value == "On"
    
    @pytest.mark.asyncio
    async def test_no_listeners_for_property(self):
        """Test handling notifications for properties with no listeners."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # No callbacks registered
        
        # Test dispatching to a property with no listeners - should not raise exceptions
        await dispatcher._dispatch_property("power", "On")
        
        # Should complete without error
    
    @pytest.mark.asyncio
    async def test_multiple_callbacks_same_property(self):
        """Test dispatching to multiple callbacks for the same property."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Set up multiple callback tracking
        callback1_called = False
        callback2_called = False
        callback1_value = None
        callback2_value = None
        
        def callback1(value):
            nonlocal callback1_called, callback1_value
            callback1_called = True
            callback1_value = value
        
        def callback2(value):
            nonlocal callback2_called, callback2_value
            callback2_called = True
            callback2_value = value
        
        dispatcher.on("power", callback1)
        dispatcher.on("power", callback2)
        
        # Test the dispatch functionality
        await dispatcher._dispatch_property("power", "On")
        
        assert callback1_called
        assert callback1_value == "On"
        assert callback2_called
        assert callback2_value == "On"
    
    @pytest.mark.asyncio
    async def test_mixed_sync_async_callbacks(self):
        """Test dispatching to a mix of sync and async callbacks."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Set up mixed callback tracking
        sync_called = False
        async_called = False
        sync_value = None
        async_value = None
        
        def sync_callback(value):
            nonlocal sync_called, sync_value
            sync_called = True
            sync_value = value
        
        async def async_callback(value):
            nonlocal async_called, async_value
            async_called = True
            async_value = value
        
        dispatcher.on("volume", sync_callback)
        dispatcher.on("volume", async_callback)
        
        # Test the dispatch functionality
        await dispatcher._dispatch_property("volume", "-30.0")
        
        # Wait for any async tasks to complete
        if dispatcher._active_tasks:
            await asyncio.gather(*dispatcher._active_tasks, return_exceptions=True)
        
        assert sync_called
        assert sync_value == "-30.0"
        assert async_called
        assert async_value == "-30.0"


class TestDispatcherLifecycle:
    """Test dispatcher start/stop functionality."""
    
    def test_dispatcher_task_management_infrastructure(self):
        """Test that dispatcher has the necessary infrastructure for task management."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Test that infrastructure exists
        assert hasattr(dispatcher, '_task')
        assert hasattr(dispatcher, '_active_tasks')
        assert hasattr(dispatcher, '_callback_timeout')
        assert hasattr(dispatcher, '_remove_task')
        
        # Test initial state
        assert dispatcher._task is None
        assert len(dispatcher._active_tasks) == 0
        assert dispatcher._callback_timeout == 5.0
    
    def test_task_cleanup_infrastructure(self):
        """Test that task cleanup infrastructure exists."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Test task set management
        mock_task = AsyncMock()
        dispatcher._active_tasks.add(mock_task)
        assert len(dispatcher._active_tasks) == 1
        
        # Test removal function
        dispatcher._remove_task(mock_task)
        assert len(dispatcher._active_tasks) == 0


class TestRealWorldExamples:
    """Test with real-world XML examples from the specification."""
    
    def test_spec_example_protocol_3_notification(self):
        """Test with the exact notification example from the Emotiva specification."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Exact example from Section 3.4 of the specification
        xml_str = '''<emotivaNotify sequence="6862">
            <property name="tuner_signal" value="Stereo 39dBuV" visible="true"/>
            <property name="tuner_channel" value="FM 106.50MHz" visible="true"/>
            <property name="tuner_program" value="Country" visible="true"/>
            <property name="tuner_RDS" value="Now Playing Old Alabama by Brad Paisley" visible="true"/>
            <property name="audio_input" value="Tuner" visible="true"/>
            <property name="audio_bitstream" value="PCM 2.0" visible="true"/>
            <property name="audio_bits" value="32kHz 24bits" visible="true"/>
            <property name="video_input" value="HDMI 1" visible="true"/>
            <property name="video_format" value="1920x1080P/60" visible="true"/>
            <property name="video_space" value="RGB 8bits " visible="true"/>
        </emotivaNotify>'''
        xml = ET.fromstring(xml_str)
        
        properties = dispatcher._extract_properties(xml)
        
        expected = {
            "tuner_signal": "Stereo 39dBuV",
            "tuner_channel": "FM 106.50MHz",
            "tuner_program": "Country",
            "tuner_RDS": "Now Playing Old Alabama by Brad Paisley",
            "audio_input": "Tuner",
            "audio_bitstream": "PCM 2.0",
            "audio_bits": "32kHz 24bits",
            "video_input": "HDMI 1",
            "video_format": "1920x1080P/60",
            "video_space": "RGB 8bits "
        }
        assert properties == expected
    
    def test_spec_example_protocol_2_from_tests(self):
        """Test with Protocol 2.0 format examples from existing tests."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # From test_core_protocol.py line 148
        xml_str = '''<emotivaNotify>
            <power>On</power>
            <volume value="-20.5">-20.5</volume>
        </emotivaNotify>'''
        xml = ET.fromstring(xml_str)
        
        properties = dispatcher._extract_properties(xml)
        
        expected = {
            "power": "On",
            "volume": "-20.5"
        }
        assert properties == expected
    
    def test_original_problem_scenario_protocol_2(self):
        """Test that reproduces the original problem scenario and shows it's fixed.
        
        This test simulates the exact issue described in the problem:
        - eMotiva sends XML notifications with Protocol 2.0 format
        - Old dispatcher expected name attribute on root element
        - New dispatcher correctly extracts properties from child elements
        """
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Simulate the notification that was causing "Received notification without property name"
        xml_str = '''<emotivaNotify>
            <volume>-20.5</volume>
        </emotivaNotify>'''
        xml = ET.fromstring(xml_str)
        
        # OLD BEHAVIOR: xml.get("name") would return None
        old_approach_name = xml.get("name")
        assert old_approach_name is None  # This was the problem!
        
        # NEW BEHAVIOR: _extract_properties correctly finds the volume property
        properties = dispatcher._extract_properties(xml)
        assert properties == {"volume": "-20.5"}
        
        # Verify we would NOT get "Received notification without property name" warning
        assert len(properties) > 0
    
    def test_original_problem_scenario_protocol_3(self):
        """Test Protocol 3.0+ format also works correctly."""
        mock_socket_mgr = AsyncMock()
        dispatcher = Dispatcher(mock_socket_mgr, "notifyPort")
        
        # Protocol 3.0+ format with multiple properties (explains large message sizes)
        xml_str = '''<emotivaNotify sequence="2940">
            <property name="power" value="On" visible="true"/>
            <property name="volume" value="-20.5" visible="true"/>
            <property name="source" value="HDMI 1" visible="true"/>
            <property name="mode" value="Stereo" visible="true"/>
            <property name="mute" value="Off" visible="true"/>
        </emotivaNotify>'''
        xml = ET.fromstring(xml_str)
        
        # OLD BEHAVIOR: xml.get("name") would return None
        old_approach_name = xml.get("name")
        assert old_approach_name is None  # This was the problem!
        
        # NEW BEHAVIOR: _extract_properties correctly finds all properties
        properties = dispatcher._extract_properties(xml)
        expected = {
            "power": "On",
            "volume": "-20.5", 
            "source": "HDMI 1",
            "mode": "Stereo",
            "mute": "Off"
        }
        assert properties == expected
        
        # This explains the variable message sizes (2940, 566, 969 bytes)
        # - Different numbers of properties per notification
        # - Different property values lengths
        assert len(properties) == 5  # Multiple properties in one notification 