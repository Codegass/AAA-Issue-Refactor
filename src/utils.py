"""Utility classes and functions."""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import List

logger = logging.getLogger('aif')

class BackupManager:
    """Manages backing up and restoring files, using memory or disk based on size."""
    def __init__(self, use_disk_threshold_mb: int = 50):
        self.threshold = use_disk_threshold_mb * 1024 * 1024
        self.use_disk = False
        self.memory_cache = {}
        self.temp_dir = None
        self.path_mapping = {}  # original_path -> backup_path

    def backup(self, file_paths: List[Path]):
        """Backs up a list of files, choosing strategy based on total size."""
        unique_paths = sorted(list(set(fp for fp in file_paths if fp and fp.exists())), key=str)
        total_size = sum(p.stat().st_size for p in unique_paths)
        
        if total_size > self.threshold:
            self.use_disk = True
            self.temp_dir = tempfile.mkdtemp(prefix="aif_backup_")
            logger.info(f"Total file size ({total_size / 1024 / 1024:.2f} MB) exceeds threshold. Using disk backup at {self.temp_dir}")
            for original_path in unique_paths:
                # Create a unique but debuggable name in temp dir to avoid collisions
                backup_name = str(original_path).replace(os.path.sep, '_').replace(':', '')
                backup_path = Path(self.temp_dir) / backup_name
                shutil.copy(original_path, backup_path)
                self.path_mapping[original_path] = backup_path
        else:
            self.use_disk = False
            logger.info("Using in-memory backup.")
            for path in unique_paths:
                self.memory_cache[path] = path.read_text(encoding='utf-8')

    def restore_file(self, file_path: Path):
        """Restores a single file from the backup."""
        if not file_path:
            return
            
        if self.use_disk:
            if file_path in self.path_mapping and self.path_mapping[file_path].exists():
                shutil.copy(self.path_mapping[file_path], file_path)
        else:
            if file_path in self.memory_cache:
                file_path.write_text(self.memory_cache[file_path], encoding='utf-8')

    def restore_all(self):
        """Restores all backed-up files."""
        logger.info("\\nPerforming final cleanup, reverting all modified files...")
        if self.use_disk:
            for original_path, backup_path in self.path_mapping.items():
                if backup_path.exists():
                    shutil.copy(backup_path, original_path)
                    logger.debug(f"  Debug: Reverted changes in '{original_path}' from disk backup.")
        else:
            for path, content in self.memory_cache.items():
                if path.exists():
                    path.write_text(content, encoding='utf-8')
                    logger.debug(f"  Debug: Reverted changes in '{path}' from memory backup.")

    def cleanup(self):
        """Removes any temporary resources (like disk backup directory)."""
        if self.use_disk and self.temp_dir:
            shutil.rmtree(self.temp_dir)
            logger.info(f"Cleaned up backup directory: {self.temp_dir}") 