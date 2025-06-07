"""Test cases for pymotivaxmc2.core.logging module."""

import pytest
import logging
from unittest.mock import patch, MagicMock

from pymotivaxmc2.core.logging import get_logger, setup_logging


class TestGetLogger:
    """Test cases for get_logger function."""

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a logger instance."""
        logger = get_logger("test_module")
        
        assert isinstance(logger, logging.Logger)
        assert logger.name == "pymotivaxmc2.test_module"

    def test_get_logger_different_modules(self):
        """Test that different module names return different loggers."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        
        assert logger1.name == "pymotivaxmc2.module1"
        assert logger2.name == "pymotivaxmc2.module2"
        assert logger1 is not logger2

    def test_get_logger_same_module_returns_same_instance(self):
        """Test that the same module name returns the same logger instance."""
        logger1 = get_logger("same_module")
        logger2 = get_logger("same_module")
        
        assert logger1 is logger2
        assert logger1.name == "pymotivaxmc2.same_module"

    def test_get_logger_empty_name(self):
        """Test get_logger with empty module name."""
        logger = get_logger("")
        
        assert logger.name == "pymotivaxmc2."

    def test_get_logger_with_dots(self):
        """Test get_logger with module name containing dots."""
        logger = get_logger("core.protocol")
        
        assert logger.name == "pymotivaxmc2.core.protocol"


class TestSetupLogging:
    """Test cases for setup_logging function."""

    def test_setup_logging_default_level(self):
        """Test setup_logging with default level."""
        setup_logging()
        
        from pymotivaxmc2.core.logging import LOGGER
        assert LOGGER.level == logging.INFO

    def test_setup_logging_debug_level(self):
        """Test setup_logging with debug level."""
        setup_logging(level=logging.DEBUG)
        
        from pymotivaxmc2.core.logging import LOGGER
        assert LOGGER.level == logging.DEBUG

    def test_setup_logging_warning_level(self):
        """Test setup_logging with warning level."""
        setup_logging(level=logging.WARNING)
        
        from pymotivaxmc2.core.logging import LOGGER
        assert LOGGER.level == logging.WARNING

    def test_setup_logging_format_contains_required_fields(self):
        """Test that setup_logging configures appropriate format."""
        setup_logging()
        
        from pymotivaxmc2.core.logging import LOGGER
        # Check that logger has handlers with proper format
        assert len(LOGGER.handlers) > 0
        handler = LOGGER.handlers[0]
        assert handler.formatter is not None
        
        format_str = handler.formatter._fmt
        # Format should contain timestamp, level, name, and message
        assert '%(asctime)s' in format_str
        assert '%(levelname)s' in format_str
        assert '%(name)s' in format_str
        assert '%(message)s' in format_str

    def test_setup_logging_multiple_calls(self):
        """Test that multiple calls to setup_logging work correctly."""
        setup_logging(level=logging.DEBUG)
        setup_logging(level=logging.INFO)
        
        from pymotivaxmc2.core.logging import LOGGER
        # Should be set to the last configured level
        assert LOGGER.level == logging.INFO

    def test_setup_logging_integration(self):
        """Test integration of setup_logging with get_logger."""
        # Setup logging
        setup_logging(level=logging.DEBUG)
        
        # Get a logger
        logger = get_logger("test_integration")
        
        # Logger should be properly configured
        assert logger.name == "pymotivaxmc2.test_integration"
        assert isinstance(logger, logging.Logger)

    def test_setup_logging_with_custom_params(self):
        """Test setup_logging with custom parameters."""
        setup_logging(
            level=logging.ERROR,
            format_string="%(name)s - %(message)s"
        )
        
        from pymotivaxmc2.core.logging import LOGGER
        assert LOGGER.level == logging.ERROR
        handler = LOGGER.handlers[0]
        assert handler.formatter._fmt == "%(name)s - %(message)s"


class TestLoggingIntegration:
    """Integration tests for logging functionality."""

    def test_logger_hierarchy(self):
        """Test that loggers follow proper hierarchy."""
        parent_logger = get_logger("parent")
        child_logger = get_logger("parent.child")
        
        assert parent_logger.name == "pymotivaxmc2.parent"
        assert child_logger.name == "pymotivaxmc2.parent.child"
        
        # Child logger should inherit from parent through logging hierarchy
        assert child_logger.parent.name.startswith("pymotivaxmc2")

    def test_logging_levels_work(self):
        """Test that different logging levels work correctly."""
        with patch('logging.basicConfig'):
            setup_logging(level=logging.DEBUG)
            
            logger = get_logger("level_test")
            
            # Test that logger has the expected methods
            assert hasattr(logger, 'debug')
            assert hasattr(logger, 'info')
            assert hasattr(logger, 'warning')
            assert hasattr(logger, 'error')
            assert hasattr(logger, 'critical')

    def test_module_specific_loggers(self):
        """Test loggers for specific modules."""
        controller_logger = get_logger("controller")
        protocol_logger = get_logger("core.protocol")
        xmlcodec_logger = get_logger("core.xmlcodec")
        
        assert controller_logger.name == "pymotivaxmc2.controller"
        assert protocol_logger.name == "pymotivaxmc2.core.protocol"
        assert xmlcodec_logger.name == "pymotivaxmc2.core.xmlcodec"
        
        # All should be different instances
        assert controller_logger is not protocol_logger
        assert protocol_logger is not xmlcodec_logger
        assert controller_logger is not xmlcodec_logger

    def test_logger_configuration_persists(self):
        """Test that logger configuration persists across multiple calls."""
        # Setup logging once
        setup_logging(level=logging.WARNING)
        
        # Get logger
        logger1 = get_logger("persist_test")
        
        # Get same logger again
        logger2 = get_logger("persist_test")
        
        # Should be the same instance
        assert logger1 is logger2 