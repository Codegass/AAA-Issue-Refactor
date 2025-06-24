"""Abstract interface for build systems."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
import logging

logger = logging.getLogger('aif')


class BuildSystem(ABC):
    """Abstract interface for Java build systems."""
    
    def __init__(self, project_path: Path):
        """Initialize the build system.
        
        Args:
            project_path: Path to the Java project root
        """
        self.project_path = project_path
        self._validate_project()
    
    @abstractmethod
    def _validate_project(self) -> None:
        """Validate that the project can be handled by this build system.
        
        Raises:
            ValueError: If the project is not compatible with this build system
        """
        pass
    
    @abstractmethod
    def get_build_system_name(self) -> str:
        """Get the name of this build system.
        
        Returns:
            Name of the build system (e.g., 'Maven', 'Gradle')
        """
        pass
    
    @abstractmethod
    def compile_project(self) -> Tuple[bool, str]:
        """Compile the Java project.
        
        Returns:
            Tuple of (success, output_message)
        """
        pass
    
    @abstractmethod
    def run_specific_test(
        self, 
        test_class: str, 
        test_method: str, 
        test_file_path: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """Run a specific test method.
        
        Args:
            test_class: Fully qualified test class name
            test_method: Test method name
            test_file_path: Optional path to the test file for module detection
            
        Returns:
            Tuple of (success, output_message)
        """
        pass
    
    @abstractmethod
    def find_module_root(self, test_file_path: Path) -> Optional[Path]:
        """Find the module root directory containing the test file.
        
        Args:
            test_file_path: Path to the test file
            
        Returns:
            Path to the module root, or None if not found
        """
        pass
    
    def get_configuration(self) -> Dict[str, Any]:
        """Get build system specific configuration.
        
        Returns:
            Dictionary of configuration parameters
        """
        return {}
    
    def clean_project(self) -> Tuple[bool, str]:
        """Clean the project (optional operation).
        
        Returns:
            Tuple of (success, output_message)
        """
        return True, "Clean operation not implemented for this build system"
    
    # New methods for build detection and smart compilation
    @abstractmethod
    def is_project_built(self) -> bool:
        """Check if the project has been successfully built."""
        pass
    
    @abstractmethod
    def check_compiled_classes(self) -> bool:
        """Check if compiled classes exist."""
        pass
    
    @abstractmethod
    def check_dependencies_resolved(self) -> bool:
        """Check if project dependencies are resolved."""
        pass
    
    @abstractmethod
    def quick_compile_test(self) -> Tuple[bool, str]:
        """Perform a quick compilation test without full build."""
        pass
    
    @abstractmethod
    def incremental_compile(self, modified_files: List[Path]) -> Tuple[bool, str]:
        """Perform incremental compilation for modified files."""
        pass
    
    @abstractmethod
    def can_load_test_class(self, test_class_name: str) -> bool:
        """Check if a test class can be loaded in the current classpath."""
        pass 