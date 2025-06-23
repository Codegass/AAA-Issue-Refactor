"""Utility classes and functions."""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple
import subprocess
import sys

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

class AutoUpdater:
    """Handles automatic updates from GitHub repository."""
    
    def __init__(self, repo_path: Optional[Path] = None, remote_url: Optional[str] = None):
        """Initialize with repository path and remote URL.
        
        Args:
            repo_path: Repository path. If None, uses current working directory.
            remote_url: Remote repository URL. If None, uses existing origin.
        """
        self.repo_path = repo_path or Path.cwd()
        self.remote_url = remote_url or "https://github.com/Codegass/AAA-Issue-Refactor.git"
        
    def is_git_repository(self) -> bool:
        """Check if current directory is a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def get_current_commit(self) -> Optional[str]:
        """Get current commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None
    
    def setup_remote(self, remote_name: str = "upstream") -> bool:
        """Setup or update the remote repository for updates."""
        try:
            # Check if remote already exists
            result = subprocess.run(
                ["git", "remote", "get-url", remote_name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                # Remote exists, update its URL
                subprocess.run(
                    ["git", "remote", "set-url", remote_name, self.remote_url],
                    cwd=self.repo_path,
                    capture_output=True,
                    timeout=10
                )
            else:
                # Remote doesn't exist, add it
                subprocess.run(
                    ["git", "remote", "add", remote_name, self.remote_url],
                    cwd=self.repo_path,
                    capture_output=True,
                    timeout=10
                )
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_remote_commit(self, branch: str = "master", remote_name: str = "upstream") -> Optional[str]:
        """Get remote commit hash for specified branch."""
        try:
            # Setup remote first
            if not self.setup_remote(remote_name):
                logger.warning("Failed to setup remote repository")
                return None
            
            # Fetch latest from remote
            subprocess.run(
                ["git", "fetch", remote_name],
                cwd=self.repo_path,
                capture_output=True,
                timeout=30
            )
            
            # Get remote commit hash
            result = subprocess.run(
                ["git", "rev-parse", f"{remote_name}/{branch}"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None
    
    def has_local_changes(self) -> bool:
        """Check if there are uncommitted local changes."""
        try:
            # Check for staged changes
            result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=self.repo_path,
                timeout=10
            )
            if result.returncode != 0:
                return True
            
            # Check for unstaged changes
            result = subprocess.run(
                ["git", "diff", "--quiet"],
                cwd=self.repo_path,
                timeout=10
            )
            if result.returncode != 0:
                return True
            
            # Check for untracked files
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
                
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True  # Assume changes exist if we can't check
        
        return False
    
    def pull_latest(self, branch: str = "master", remote_name: str = "upstream") -> Tuple[bool, str]:
        """Pull latest changes from remote repository."""
        try:
            # Setup remote first
            if not self.setup_remote(remote_name):
                return False, "Failed to setup remote repository"
                
            result = subprocess.run(
                ["git", "pull", remote_name, branch],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Git pull operation timed out"
        except FileNotFoundError:
            return False, "Git command not found"
    
    def check_and_update(self, branch: str = "master", force: bool = False, remote_name: str = "upstream") -> Tuple[bool, str]:
        """
        Check for updates and automatically pull if available.
        
        Args:
            branch: Git branch to check (default: master)
            force: Force update even with local changes (default: False)
            remote_name: Remote name to use (default: upstream)
            
        Returns:
            Tuple of (success, message)
        """
        if not self.is_git_repository():
            return False, "Not a git repository"
        
        logger.info(f"Checking GitHub updates... (from {self.remote_url})")
        
        current_commit = self.get_current_commit()
        if not current_commit:
            return False, "Cannot get current commit information"
        
        remote_commit = self.get_remote_commit(branch, remote_name)
        if not remote_commit:
            return False, "Cannot get remote commit information, possibly network connection issues"
        
        if current_commit == remote_commit:
            logger.info("✓ Current version is up to date")
            return True, "Already up to date"
        
        logger.info(f"New version found, preparing update... (current: {current_commit[:8]}, latest: {remote_commit[:8]})")
        
        # Check for local changes
        if not force and self.has_local_changes():
            logger.warning("⚠ Local changes detected, skipping automatic update")
            logger.warning("Please commit or revert local changes, or use --force-update to force update")
            return False, "Local changes detected, skipping update"
        
        # Perform the update
        success, output = self.pull_latest(branch, remote_name)
        if success:
            logger.info("✓ Update successful!")
            logger.info("Restarting program to use latest version...")
            return True, "Update successful"
        else:
            logger.error(f"✗ Update failed: {output}")
            return False, f"Update failed: {output}"

def check_and_auto_update(force: bool = False) -> bool:
    """
    Check for updates and auto-update if available.
    
    Args:
        force: Force update even with local changes
        
    Returns:
        True if update was performed, False otherwise
    """
    updater = AutoUpdater()
    success, message = updater.check_and_update(force=force)
    
    if success and "Update successful" in message:
        # Restart the program after successful update
        logger.info("Restarting program...")
        python = sys.executable
        subprocess.Popen([python] + sys.argv)
        sys.exit(0)
    
    return success 