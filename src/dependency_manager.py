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
        """Add Hamcrest dependency to the project and ALL submodules."""
        if self.build_system == "maven":
            return self._add_hamcrest_maven_all_modules()
        elif self.build_system == "gradle":
            return self._add_hamcrest_gradle_all_modules()
        else:
            return False, f"Unsupported build system: {self.build_system}"
    
    def _add_hamcrest_maven_all_modules(self) -> Tuple[bool, str]:
        """Add Hamcrest dependency to all Maven pom.xml files found in the project."""
        # Find all pom.xml files in the project
        all_poms = list(self.project_path.glob("**/pom.xml"))
        
        if not all_poms:
            return False, "No pom.xml files found"
        
        logger.info(f"Found {len(all_poms)} pom.xml files to process")
        
        modified_files = []
        already_present = []
        failed_files = []
        
        for pom_file in all_poms:
            try:
                # Skip backup directories to avoid modifying backups
                if '.aif_backup' in str(pom_file) or 'backup' in str(pom_file).lower():
                    continue
                
                relative_path = pom_file.relative_to(self.project_path)
                logger.debug(f"Processing: {relative_path}")
                
                # Backup original file
                self._backup_file(pom_file)
                
                content = pom_file.read_text(encoding='utf-8')
                
                # Check if hamcrest is already present
                if self._is_hamcrest_present_maven(content):
                    logger.debug(f"  Hamcrest already present in {relative_path}")
                    already_present.append(str(relative_path))
                    continue
                
                # Check if our marker is already present
                if self.MAVEN_START_MARKER in content:
                    logger.debug(f"  Our Hamcrest already added to {relative_path}")
                    already_present.append(str(relative_path))
                    continue
                
                # Try to add hamcrest
                modified_content = self._insert_hamcrest_maven_minimal(content)
                
                if modified_content != content:
                    pom_file.write_text(modified_content, encoding='utf-8')
                    modified_files.append(str(relative_path))
                    logger.debug(f"  ✓ Added Hamcrest to {relative_path}")
                else:
                    logger.debug(f"  ✗ Could not modify {relative_path}")
                    failed_files.append(str(relative_path))
                    
            except Exception as e:
                logger.error(f"Failed to process {pom_file}: {e}")
                failed_files.append(str(pom_file.relative_to(self.project_path)))
        
        # Create summary message
        summary_parts = []
        if modified_files:
            summary_parts.append(f"Added to {len(modified_files)} modules: {', '.join(modified_files[:3])}" + 
                                ("..." if len(modified_files) > 3 else ""))
        if already_present:
            summary_parts.append(f"Already present in {len(already_present)} modules")
        if failed_files:
            summary_parts.append(f"Failed to modify {len(failed_files)} modules")
        
        if modified_files or already_present:
            return True, "; ".join(summary_parts)
        else:
            return False, f"Failed to add Hamcrest to any modules: {'; '.join(summary_parts)}"
    
    def _add_hamcrest_gradle_all_modules(self) -> Tuple[bool, str]:
        """Add Hamcrest dependency to all Gradle build files found in the project."""
        # Find all build.gradle and build.gradle.kts files
        gradle_files = list(self.project_path.glob("**/build.gradle")) + \
                      list(self.project_path.glob("**/build.gradle.kts"))
        
        if not gradle_files:
            return False, "No build.gradle files found"
        
        logger.info(f"Found {len(gradle_files)} Gradle build files to process")
        
        modified_files = []
        already_present = []
        failed_files = []
        
        for gradle_file in gradle_files:
            try:
                # Skip backup directories
                if '.aif_backup' in str(gradle_file) or 'backup' in str(gradle_file).lower():
                    continue
                
                relative_path = gradle_file.relative_to(self.project_path)
                logger.debug(f"Processing: {relative_path}")
                
                # Backup original file
                self._backup_file(gradle_file)
                
                content = gradle_file.read_text(encoding='utf-8')
                
                # Check if hamcrest is already present
                if 'org.hamcrest' in content or 'hamcrest' in content:
                    # Check if it's an old version that needs upgrading
                    if 'hamcrest-all' in content and 'hamcrestVersion' in content:
                        logger.debug(f"  Found old hamcrest-all in {relative_path}, will upgrade")
                        # Continue to upgrade
                    elif 'hamcrest:2.2' in content or 'AAA-Issue-Refactor' in content:
                        logger.debug(f"  Modern Hamcrest already present in {relative_path}")
                        already_present.append(str(relative_path))
                        continue
                    else:
                        logger.debug(f"  Unknown hamcrest version in {relative_path}, will upgrade")
                        # Continue to upgrade
                
                # Try to add hamcrest
                modified_content = self._add_to_gradle_dependencies(content)
                
                if modified_content != content:
                    gradle_file.write_text(modified_content, encoding='utf-8')
                    modified_files.append(str(relative_path))
                    logger.debug(f"  ✓ Added Hamcrest to {relative_path}")
                else:
                    logger.debug(f"  ✗ Could not modify {relative_path} (no dependencies block found)")
                    failed_files.append(str(relative_path))
                    
            except Exception as e:
                logger.error(f"Failed to process {gradle_file}: {e}")
                failed_files.append(str(gradle_file.relative_to(self.project_path)))
        
        # Create summary message
        summary_parts = []
        if modified_files:
            summary_parts.append(f"Added to {len(modified_files)} modules: {', '.join(modified_files[:3])}" + 
                                ("..." if len(modified_files) > 3 else ""))
        if already_present:
            summary_parts.append(f"Already present in {len(already_present)} modules")
        if failed_files:
            summary_parts.append(f"Failed to modify {len(failed_files)} modules")
        
        if modified_files or already_present:
            return True, "; ".join(summary_parts)
        else:
            return False, f"Failed to add Hamcrest to any modules: {'; '.join(summary_parts)}"
    
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
    
    def _add_to_gradle_dependencies(self, content: str) -> str:
        """Add Hamcrest to Gradle dependencies block."""
        lines = content.split('\n')
        
        # Check if there's already hamcrest-all and upgrade it
        hamcrest_upgraded = False
        for i, line in enumerate(lines):
            if 'hamcrest-all' in line and ('testCompile' in line or 'testImplementation' in line):
                # Replace old hamcrest-all with modern hamcrest
                old_line = line
                # Extract indentation
                indent_match = re.match(r'^(\s*)', line)
                indent = indent_match.group(1) if indent_match else "    "
                
                # Replace with modern hamcrest version
                if 'testCompile' in line:
                    new_line = f'{indent}testImplementation "org.hamcrest:hamcrest:2.2"  // Upgraded from hamcrest-all for AAA-Issue-Refactor'
                else:
                    new_line = f'{indent}testImplementation "org.hamcrest:hamcrest:2.2"  // Upgraded from hamcrest-all for AAA-Issue-Refactor'
                
                lines[i] = f'    // {old_line.strip()}  // Commented out by AAA-Issue-Refactor'
                lines.insert(i + 1, new_line)
                hamcrest_upgraded = True
                logger.debug(f"Upgraded hamcrest-all to hamcrest:2.2")
                break
        
        if hamcrest_upgraded:
            return '\n'.join(lines)
        
        # If no existing hamcrest found, add new dependency
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