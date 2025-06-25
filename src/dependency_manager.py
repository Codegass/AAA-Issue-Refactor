"""Dependency management for adding temporary test dependencies."""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging
import re

logger = logging.getLogger('aif')

class DependencyManager:
    """Manages temporary dependency additions for Maven and Gradle projects."""
    
    HAMCREST_MAVEN_DEPENDENCY = """        <dependency>
            <groupId>org.hamcrest</groupId>
            <artifactId>hamcrest</artifactId>
            <version>2.2</version>
            <scope>test</scope>
        </dependency>"""
    
    HAMCREST_GRADLE = "testImplementation 'org.hamcrest:hamcrest:2.2'"
    
    # Marker comments to identify our additions
    MAVEN_START_MARKER = "        <!-- AAA-Issue-Refactor: Hamcrest dependency START -->"
    MAVEN_END_MARKER = "        <!-- AAA-Issue-Refactor: Hamcrest dependency END -->"
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.build_system = self._detect_build_system()
        self.backup_files: List[Path] = []
        
    def _detect_build_system(self) -> str:
        """Detect the build system used."""
        if (self.project_path / "pom.xml").exists():
            return "maven"
        elif any(self.project_path.glob("**/build.gradle*")):
            return "gradle"
        else:
            return "unknown"
    
    def add_hamcrest_dependency(self) -> Tuple[bool, str]:
        """Add Hamcrest dependency to the project temporarily."""
        if self.build_system == "maven":
            return self._add_hamcrest_maven()
        elif self.build_system == "gradle":
            return self._add_hamcrest_gradle()
        else:
            return False, f"Unsupported build system: {self.build_system}"
    
    def _add_hamcrest_maven(self) -> Tuple[bool, str]:
        """Add Hamcrest dependency to Maven pom.xml using minimal string modification."""
        # Only modify the root pom.xml, not all sub-modules
        root_pom = self.project_path / "pom.xml"
        if not root_pom.exists():
            return False, "Root pom.xml not found"
        
        try:
            # Backup original file
            self._backup_file(root_pom)
            
            content = root_pom.read_text(encoding='utf-8')
            
            # Check if hamcrest is already present (more comprehensive check)
            if self._is_hamcrest_present_maven(content):
                logger.debug("Hamcrest already present in root pom.xml")
                return True, "Hamcrest dependency already present"
            
            # Check if our marker is already present (we added it before)
            if self.MAVEN_START_MARKER in content:
                logger.debug("Our Hamcrest dependency already added")
                return True, "Hamcrest dependency already added by tool"
            
            # Find dependencies section and add hamcrest with minimal modification
            modified_content = self._insert_hamcrest_maven_minimal(content)
            
            if modified_content != content:
                root_pom.write_text(modified_content, encoding='utf-8')
                return True, "Added Hamcrest to root pom.xml with minimal modification"
            else:
                return False, "Could not find appropriate location to add Hamcrest dependency"
                
        except Exception as e:
            logger.error(f"Failed to modify {root_pom}: {e}")
            return False, f"Error modifying pom.xml: {e}"
    
    def _is_hamcrest_present_maven(self, content: str) -> bool:
        """Check if Hamcrest dependency is already present in Maven POM."""
        # Look for various forms of hamcrest dependency
        hamcrest_patterns = [
            r'<groupId>\s*org\.hamcrest\s*</groupId>',
            r'hamcrest-.*?</artifactId>',
            r'<artifactId>\s*hamcrest\s*</artifactId>'
        ]
        
        for pattern in hamcrest_patterns:
            if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                return True
        return False
    
    def _insert_hamcrest_maven_minimal(self, content: str) -> str:
        """Insert Hamcrest dependency using minimal string modification."""
        lines = content.split('\n')
        
        # Find the dependencies section
        in_dependencies = False
        dependencies_start = -1
        dependencies_end = -1
        indent = "        "  # Default Maven indent
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Find start of dependencies section
            if stripped == '<dependencies>' or stripped.startswith('<dependencies '):
                in_dependencies = True
                dependencies_start = i
                # Extract indentation from the dependencies tag
                match = re.match(r'^(\s*)', line)
                if match:
                    base_indent = match.group(1)
                    indent = base_indent + "    "  # Add one level of indentation
                continue
            
            # Find end of dependencies section
            if in_dependencies and stripped == '</dependencies>':
                dependencies_end = i
                break
        
        if dependencies_start == -1:
            # No dependencies section found, need to create one
            return self._create_dependencies_section_maven(content)
        
        if dependencies_end == -1:
            # Malformed XML, dependencies section not closed
            return content
        
        # Insert our dependency just before </dependencies>
        hamcrest_block = [
            self.MAVEN_START_MARKER,
            self.HAMCREST_MAVEN_DEPENDENCY,
            self.MAVEN_END_MARKER
        ]
        
        # Insert at the end of dependencies section
        for block_line in reversed(hamcrest_block):
            lines.insert(dependencies_end, block_line)
        
        return '\n'.join(lines)
    
    def _create_dependencies_section_maven(self, content: str) -> str:
        """Create a new dependencies section if it doesn't exist."""
        lines = content.split('\n')
        
        # Find a good place to insert dependencies (after properties or before build)
        insertion_point = -1
        base_indent = "    "  # Default indent
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Look for end of properties or start of build/plugins
            if (stripped == '</properties>' or 
                stripped in ['<build>', '<build >', '<profiles>', '<profiles >']):
                insertion_point = i + 1
                # Extract base indentation
                match = re.match(r'^(\s*)', line)
                if match:
                    base_indent = match.group(1)
                break
        
        if insertion_point == -1:
            # Fallback: insert before </project>
            for i, line in enumerate(lines):
                if line.strip() == '</project>':
                    insertion_point = i
                    break
        
        if insertion_point == -1:
            return content  # Cannot find insertion point
        
        # Create full dependencies section
        dependencies_section = [
            "",  # Empty line for separation
            f"{base_indent}<dependencies>",
            self.MAVEN_START_MARKER,
            self.HAMCREST_MAVEN_DEPENDENCY,
            self.MAVEN_END_MARKER,
            f"{base_indent}</dependencies>"
        ]
        
        # Insert the section
        for dep_line in reversed(dependencies_section):
            lines.insert(insertion_point, dep_line)
        
        return '\n'.join(lines)
    
    def _add_hamcrest_gradle(self) -> Tuple[bool, str]:
        """Add Hamcrest dependency to Gradle build files."""
        # Only modify the root build.gradle file
        root_gradle = self.project_path / "build.gradle"
        if not root_gradle.exists():
            # Try build.gradle.kts
            root_gradle = self.project_path / "build.gradle.kts"
            if not root_gradle.exists():
                return False, "Root build.gradle or build.gradle.kts not found"
        
        try:
            # Backup original file
            self._backup_file(root_gradle)
            
            content = root_gradle.read_text(encoding='utf-8')
            
            # Check if hamcrest is already present
            if 'org.hamcrest' in content or 'hamcrest' in content:
                logger.debug("Hamcrest already present in root build.gradle")
                return True, "Hamcrest dependency already present"
            
            # Find dependencies block and add hamcrest
            modified_content = self._add_to_gradle_dependencies(content)
            
            if modified_content != content:
                root_gradle.write_text(modified_content, encoding='utf-8')
                return True, "Added Hamcrest to root build.gradle"
            else:
                return False, "Could not find dependencies block in build.gradle"
                
        except Exception as e:
            logger.error(f"Failed to modify {root_gradle}: {e}")
            return False, f"Error modifying build.gradle: {e}"
    
    def _add_to_gradle_dependencies(self, content: str) -> str:
        """Add Hamcrest to Gradle dependencies block."""
        lines = content.split('\n')
        
        # Find dependencies block
        in_dependencies = False
        brace_count = 0
        insertion_line = -1
        base_indent = "    "
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            if not in_dependencies and stripped.startswith('dependencies'):
                in_dependencies = True
                brace_count = 0
                # Extract indentation
                match = re.match(r'^(\s*)', line)
                if match:
                    base_indent = match.group(1) + "    "
                continue
            
            if in_dependencies:
                brace_count += line.count('{') - line.count('}')
                
                # Look for test dependencies section or any test dependency
                if ('test' in stripped.lower() and 
                    ('implementation' in stripped or 'compile' in stripped or 'api' in stripped)):
                    insertion_line = i + 1
                
                # End of dependencies block
                if brace_count == 0:
                    if insertion_line == -1:
                        # No test dependencies found, insert before closing brace
                        insertion_line = i
                    break
        
        if insertion_line != -1:
            # Add comment and dependency
            hamcrest_lines = [
                f"{base_indent}// AAA-Issue-Refactor: Temporary Hamcrest dependency",
                f"{base_indent}{self.HAMCREST_GRADLE}"
            ]
            
            for line_to_insert in reversed(hamcrest_lines):
                lines.insert(insertion_line, line_to_insert)
            
            return '\n'.join(lines)
        
        return content
    
    def _backup_file(self, file_path: Path):
        """Backup a file before modification."""
        backup_path = file_path.with_suffix(file_path.suffix + '.aif_backup')
        backup_path.write_text(file_path.read_text(encoding='utf-8'), encoding='utf-8')
        self.backup_files.append(backup_path)
        logger.debug(f"Backed up {file_path} to {backup_path}")
    
    def restore_backups(self):
        """Restore all backed up files."""
        restored = []
        for backup_path in self.backup_files:
            try:
                original_path = backup_path.with_suffix('')
                original_path = original_path.with_suffix(original_path.suffix.replace('.aif_backup', ''))
                
                original_path.write_text(backup_path.read_text(encoding='utf-8'), encoding='utf-8')
                backup_path.unlink()  # Remove backup file
                restored.append(original_path.name)
                
            except Exception as e:
                logger.error(f"Failed to restore {backup_path}: {e}")
        
        if restored:
            logger.info(f"Restored {len(restored)} files: {', '.join(restored)}")
        
        self.backup_files.clear()
    
    def cleanup(self):
        """Clean up any remaining backup files."""
        for backup_path in self.backup_files:
            try:
                if backup_path.exists():
                    backup_path.unlink()
            except Exception as e:
                logger.debug(f"Failed to cleanup backup {backup_path}: {e}")
        
        self.backup_files.clear() 