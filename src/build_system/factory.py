"""Build system factory for automatic detection and creation."""

from pathlib import Path
from typing import Optional
import logging

from .interface import BuildSystem
from .maven_build import MavenBuildSystem
from .gradle_build import GradleBuildSystem

logger = logging.getLogger('aif')


def detect_build_system_type(project_path: Path) -> Optional[str]:
    """Detect the build system type for a given project.
    
    Args:
        project_path: Path to the Java project root
        
    Returns:
        The build system type ('maven', 'gradle') or None if not detected
    """
    if (project_path / "pom.xml").exists():
        return "maven"
    elif ((project_path / "build.gradle").exists() or 
          (project_path / "build.gradle.kts").exists()):
        return "gradle"
    else:
        return None


def create_build_system(project_path: Path, build_system_type: Optional[str] = None) -> BuildSystem:
    """Create the appropriate build system instance.
    
    Args:
        project_path: Path to the Java project root
        build_system_type: Optional override for build system type detection
        
    Returns:
        An instance of the appropriate build system
        
    Raises:
        ValueError: If no suitable build system is detected or supported
    """
    if build_system_type is None:
        build_system_type = detect_build_system_type(project_path)
    
    if build_system_type == "maven":
        logger.debug(f"Creating Maven build system for project: {project_path}")
        return MavenBuildSystem(project_path)
    elif build_system_type == "gradle":
        logger.debug(f"Creating Gradle build system for project: {project_path}")
        return GradleBuildSystem(project_path)
    else:
        available_files = []
        if (project_path / "pom.xml").exists():
            available_files.append("pom.xml")
        if (project_path / "build.gradle").exists():
            available_files.append("build.gradle")
        if (project_path / "build.gradle.kts").exists():
            available_files.append("build.gradle.kts")
        
        if available_files:
            error_msg = (f"Found build files {available_files} in {project_path}, "
                        f"but could not determine build system type")
        else:
            error_msg = (f"No supported build system detected in {project_path}. "
                        f"Expected pom.xml (Maven) or build.gradle/build.gradle.kts (Gradle)")
        
        raise ValueError(error_msg) 