"""Test cases for pymotivaxmc2.exceptions module."""

import pytest
from pymotivaxmc2.exceptions import (
    EmotivaError,
    AckTimeoutError,
    InvalidArgumentError,
    InvalidCommandError,
    DeviceOfflineError,
)


class TestEmotivaError:
    """Test cases for EmotivaError base exception."""

    def test_inheritance(self):
        """Test that EmotivaError inherits from Exception."""
        assert issubclass(EmotivaError, Exception)

    def test_instantiation(self):
        """Test that EmotivaError can be instantiated."""
        error = EmotivaError("Test error message")
        assert str(error) == "Test error message"

    def test_raising(self):
        """Test that EmotivaError can be raised and caught."""
        with pytest.raises(EmotivaError) as excinfo:
            raise EmotivaError("Test error")
        assert str(excinfo.value) == "Test error"

    def test_empty_message(self):
        """Test EmotivaError with empty message."""
        error = EmotivaError()
        assert str(error) == ""


class TestAckTimeoutError:
    """Test cases for AckTimeoutError."""

    def test_inheritance(self):
        """Test that AckTimeoutError inherits from EmotivaError."""
        assert issubclass(AckTimeoutError, EmotivaError)
        assert issubclass(AckTimeoutError, Exception)

    def test_instantiation(self):
        """Test that AckTimeoutError can be instantiated."""
        error = AckTimeoutError("Timeout waiting for ack")
        assert str(error) == "Timeout waiting for ack"

    def test_raising(self):
        """Test that AckTimeoutError can be raised and caught."""
        with pytest.raises(AckTimeoutError) as excinfo:
            raise AckTimeoutError("Command timeout")
        assert str(excinfo.value) == "Command timeout"

    def test_catches_as_base_exception(self):
        """Test that AckTimeoutError can be caught as EmotivaError."""
        with pytest.raises(EmotivaError):
            raise AckTimeoutError("Test timeout")


class TestInvalidArgumentError:
    """Test cases for InvalidArgumentError."""

    def test_inheritance(self):
        """Test that InvalidArgumentError inherits from EmotivaError."""
        assert issubclass(InvalidArgumentError, EmotivaError)
        assert issubclass(InvalidArgumentError, Exception)

    def test_instantiation(self):
        """Test that InvalidArgumentError can be instantiated."""
        error = InvalidArgumentError("Invalid argument provided")
        assert str(error) == "Invalid argument provided"

    def test_raising(self):
        """Test that InvalidArgumentError can be raised and caught."""
        with pytest.raises(InvalidArgumentError) as excinfo:
            raise InvalidArgumentError("Bad argument")
        assert str(excinfo.value) == "Bad argument"

    def test_catches_as_base_exception(self):
        """Test that InvalidArgumentError can be caught as EmotivaError."""
        with pytest.raises(EmotivaError):
            raise InvalidArgumentError("Test invalid argument")


class TestInvalidCommandError:
    """Test cases for InvalidCommandError."""

    def test_inheritance(self):
        """Test that InvalidCommandError inherits from EmotivaError."""
        assert issubclass(InvalidCommandError, EmotivaError)
        assert issubclass(InvalidCommandError, Exception)

    def test_instantiation(self):
        """Test that InvalidCommandError can be instantiated."""
        error = InvalidCommandError("Invalid command")
        assert str(error) == "Invalid command"

    def test_raising(self):
        """Test that InvalidCommandError can be raised and caught."""
        with pytest.raises(InvalidCommandError) as excinfo:
            raise InvalidCommandError("Bad command")
        assert str(excinfo.value) == "Bad command"

    def test_catches_as_base_exception(self):
        """Test that InvalidCommandError can be caught as EmotivaError."""
        with pytest.raises(EmotivaError):
            raise InvalidCommandError("Test invalid command")


class TestDeviceOfflineError:
    """Test cases for DeviceOfflineError."""

    def test_inheritance(self):
        """Test that DeviceOfflineError inherits from EmotivaError."""
        assert issubclass(DeviceOfflineError, EmotivaError)
        assert issubclass(DeviceOfflineError, Exception)

    def test_instantiation(self):
        """Test that DeviceOfflineError can be instantiated."""
        error = DeviceOfflineError("Device offline")
        assert str(error) == "Device offline"

    def test_raising(self):
        """Test that DeviceOfflineError can be raised and caught."""
        with pytest.raises(DeviceOfflineError) as excinfo:
            raise DeviceOfflineError("Device is offline")
        assert str(excinfo.value) == "Device is offline"

    def test_catches_as_base_exception(self):
        """Test that DeviceOfflineError can be caught as EmotivaError."""
        with pytest.raises(EmotivaError):
            raise DeviceOfflineError("Test device offline")


class TestExceptionHierarchy:
    """Test cases for the exception hierarchy."""

    def test_all_exceptions_inherit_from_base(self):
        """Test that all exceptions inherit from EmotivaError."""
        exceptions = [
            AckTimeoutError,
            InvalidArgumentError,
            InvalidCommandError,
            DeviceOfflineError,
        ]
        
        for exc_class in exceptions:
            assert issubclass(exc_class, EmotivaError)
            assert issubclass(exc_class, Exception)

    def test_exception_catching_order(self):
        """Test that specific exceptions are caught before base exception."""
        # Test that we can catch specific exceptions
        with pytest.raises(AckTimeoutError):
            raise AckTimeoutError("Test")
            
        # Test that we can catch all as base exception
        with pytest.raises(EmotivaError):
            raise AckTimeoutError("Test")
            
        with pytest.raises(EmotivaError):
            raise InvalidArgumentError("Test")
            
        with pytest.raises(EmotivaError):
            raise InvalidCommandError("Test")
            
        with pytest.raises(EmotivaError):
            raise DeviceOfflineError("Test") 