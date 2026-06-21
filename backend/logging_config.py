"""
Centralized logging configuration for FinSage AI.
Sets up console and file logging using settings from config.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from backend.config import settings

def setup_logging(log_level_override: Optional[str] = None) -> None:
    """
    Configure global logging with a stream handler (console) and an optional
    rotating file handler.
    """
    # Determine the log level
    level_name = log_level_override or settings.log_level
    log_level = getattr(logging, level_name.upper(), logging.INFO)
    
    # Common log format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    formatter = logging.Formatter(log_format)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers to prevent duplicate logs
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        
    # Console/Stream handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # File handler
    if settings.log_file:
        # Resolve path relative to the project root directory
        # Project root is the parent of backend/
        project_root = Path(__file__).resolve().parent.parent
        log_path = project_root / settings.log_file
        
        try:
            # Ensure the directory exists
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Rotating file handler (10MB per file, max 5 backup files)
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(log_level)
            root_logger.addHandler(file_handler)
            
            # Log successful initialization of file logging
            logging.getLogger(__name__).info(f"Logging initialized. Log file path: {log_path}")
        except Exception as e:
            # Fallback output to stdout if log file cannot be created/written to
            logging.getLogger(__name__).error(f"Failed to initialize file logger at {log_path}: {e}")
            
    # Configure Uvicorn logging handlers to bubble up to root
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        ulogger = logging.getLogger(uvicorn_logger_name)
        ulogger.handlers = []
        ulogger.propagate = True
