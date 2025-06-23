"""Logging configuration for the application."""

import logging
import sys
from pathlib import Path
from datetime import datetime

def setup_logger(output_path: Path, debug_mode: bool = False):
    """
    Configure the logger for the application.

    Args:
        output_path: The directory where logs will be stored.
        debug_mode: If True, sets logging level to DEBUG and enables file logging.
    """
    logger = logging.getLogger('aif')
    logger.handlers.clear()  # Prevent duplicate handlers across runs
    
    # Set level based on debug mode
    log_level = logging.DEBUG if debug_mode else logging.INFO
    logger.setLevel(log_level)
    
    # Console Handler - always on, shows INFO or DEBUG
    console_handler = logging.StreamHandler(sys.stdout)
    # Use a simple formatter for console to keep output clean
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)

    if debug_mode:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = output_path / f"aif_debug_{timestamp}.log"
        
        # File Handler - only in debug mode
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        # Use a detailed formatter for the log file
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        
        # Announce the log file creation via the logger itself
        logger.info(f"✓ Debug mode enabled. Detailed logs will be saved to: {log_file}")
        
    return logger 