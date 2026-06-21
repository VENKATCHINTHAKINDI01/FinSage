import os
import logging
import pytest
from pathlib import Path
from backend.config import settings
from backend.logging_config import setup_logging

def test_logging_setup(tmp_path):
    # Backup the original config values
    original_log_file = settings.log_file
    original_log_level = settings.log_level
    
    try:
        # Define a temporary log file path inside tmp_path
        test_log_file = tmp_path / "test_finsage.log"
        
        # Set config override
        settings.log_file = str(test_log_file)
        settings.log_level = "DEBUG"
        
        # Initialize logging
        setup_logging()
        
        # Get logger and write some log messages
        logger = logging.getLogger("test_logger")
        test_message = "Testing global logging file configuration - Hello FinSage!"
        logger.info(test_message)
        logger.debug("This is a debug message")
        
        # Flush handlers to ensure logs are written to disk
        for handler in logging.getLogger().handlers:
            handler.flush()
            if hasattr(handler, "close"):
                handler.close()
            
        # Verify the log file was created
        assert test_log_file.exists(), "Log file was not created"
        
        # Verify the contents of the log file
        log_contents = test_log_file.read_text(encoding="utf-8")
        assert test_message in log_contents, f"Log message not found in log file: {log_contents}"
        assert "INFO" in log_contents
        assert "This is a debug message" in log_contents
        assert "DEBUG" in log_contents
        
    finally:
        # Restore configuration
        settings.log_file = original_log_file
        settings.log_level = original_log_level
        # Re-initialize logging back to default settings
        setup_logging()
