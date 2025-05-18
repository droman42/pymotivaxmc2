"""Logging configuration for the pymotivaxmc2 library."""
import logging
import sys
from typing import Optional, List, Union

# Library logger
LOGGER = logging.getLogger("pymotivaxmc2")

# Default log format
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

def setup_logging(
    level: Union[int, str] = logging.INFO,
    format_string: str = DEFAULT_FORMAT,
    handlers: Optional[List[logging.Handler]] = None,
    show_xml: bool = False,
) -> None:
    """Configure logging for the pymotivaxmc2 library.
    
    Args:
        level: Logging level (default: INFO)
        format_string: Log format string
        handlers: List of log handlers (default: StreamHandler to stdout)
        show_xml: Whether to show full XML payloads in logs
    """
    # Convert string level to int if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    
    # Set up library logger
    LOGGER.setLevel(level)
    
    # Clear existing handlers
    for handler in list(LOGGER.handlers):
        LOGGER.removeHandler(handler)
    
    # Add default handler if none provided
    if not handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(format_string))
        handlers = [handler]
    
    # Add all handlers
    for handler in handlers:
        LOGGER.addHandler(handler)
    
    # Set XML debug flag
    global SHOW_XML
    SHOW_XML = show_xml
    
    # Log initial setup
    LOGGER.debug(
        "Logging initialized: level=%s, format=%s, show_xml=%s",
        logging.getLevelName(level),
        format_string,
        show_xml,
    )

# Module flags
SHOW_XML = False

def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module.
    
    Args:
        name: Module name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(f"pymotivaxmc2.{name}")

def log_xml(logger: logging.Logger, direction: str, xml_data: Union[str, bytes], level: int = logging.DEBUG) -> None:
    """Log XML data if XML debugging is enabled.
    
    Args:
        logger: Logger instance
        direction: Direction ('sent' or 'received')
        xml_data: XML data to log
        level: Logging level
    """
    if not SHOW_XML or not logger.isEnabledFor(level):
        return
    
    if isinstance(xml_data, bytes):
        xml_data = xml_data.decode("utf-8", errors="replace")
    
    logger.log(level, "%s XML: %s", direction.upper(), xml_data.strip()) 