"""Dependency management for adding temporary test dependencies."""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
import logging
import re

logger = logging.getLogger('aif')

class DependencyManager:
    """Manages temporary dependency additions for Maven and Gradle projects."""
    
    # Use Hamcrest 2.2 which has org.hamcrest.Matchers
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
        self.existing_hamcrest_info = None  # Will store detected Hamcrest info
        
    def _detect_build_system(self) -> str:
        """Detect the build system used."""
        if (self.project_path / "pom.xml").exists():
            return "maven"
        elif any(self.project_path.glob("**/build.gradle*")):
            return "gradle"
        else:
            return "unknown"
    
    def _detect_existing_hamcrest_dependency(self) -> Dict[str, Any]:
        """
        Detect existing Hamcrest dependencies in the project.
        Returns info about existing Hamcrest versions and formats.
        """
        hamcrest_info = {
            "exists": False,
            "version": None,
            "format": None,  # "hamcrest" (2.x) or "hamcrest-all" (1.x)
            "compatible": False,
            "files_checked": []
        }
        
        if self.build_system == "gradle":
            return self._detect_hamcrest_gradle(hamcrest_info)
        elif self.build_system == "maven":
            return self._detect_hamcrest_maven(hamcrest_info)
        
        return hamcrest_info
    
    def _detect_hamcrest_gradle(self, hamcrest_info: Dict[str, Any]) -> Dict[str, Any]:
        """Detect Hamcrest in Gradle projects."""
        # Check main build.gradle
        main_build_gradle = self.project_path / "build.gradle"
        if main_build_gradle.exists():
            hamcrest_info["files_checked"].append(str(main_build_gradle))
            content = main_build_gradle.read_text(encoding='utf-8')
            self._parse_gradle_hamcrest(content, hamcrest_info)
        
        # Check dependency version files
        dep_version_files = [
            self.project_path / "gradle" / "dependency-versions.gradle",
            self.project_path / "gradle.properties"
        ]
        
        for dep_file in dep_version_files:
            if dep_file.exists():
                hamcrest_info["files_checked"].append(str(dep_file))
                content = dep_file.read_text(encoding='utf-8')
                # Look for hamcrestVersion definition
                version_match = re.search(r'hamcrestVersion\s*=\s*["\']([^"\']+)["\']', content)
                if version_match:
                    hamcrest_info["version"] = version_match.group(1)
        
        # Check if all subproject build files
        for gradle_file in self.project_path.glob("**/build.gradle*"):
            if "build" in str(gradle_file) or ".gradle" in str(gradle_file).replace(str(gradle_file.name), ""):
                continue  # Skip build output directories
            hamcrest_info["files_checked"].append(str(gradle_file))
            content = gradle_file.read_text(encoding='utf-8')
            self._parse_gradle_hamcrest(content, hamcrest_info)
        
        return hamcrest_info
    
    def _parse_gradle_hamcrest(self, content: str, hamcrest_info: Dict[str, Any]):
        """Parse Gradle build file content for Hamcrest dependencies."""
        # Look for various Hamcrest dependency patterns
        hamcrest_patterns = [
            (r'["\']org\.hamcrest:hamcrest:([^"\']+)["\']', "hamcrest"),
            (r'["\']org\.hamcrest:hamcrest-all:([^"\']+)["\']', "hamcrest-all"),
            (r'["\']org\.hamcrest:hamcrest-core:([^"\']+)["\']', "hamcrest-core"),
            (r'["\']org\.hamcrest:hamcrest-library:([^"\']+)["\']', "hamcrest-library"),
        ]
        
        for pattern, format_type in hamcrest_patterns:
            matches = re.findall(pattern, content)
            if matches:
                hamcrest_info["exists"] = True
                hamcrest_info["format"] = format_type
                # Use version from dependency if not found in version file
                if not hamcrest_info["version"] and matches:
                    version = matches[0]
                    # Handle variable references like $hamcrestVersion
                    if version.startswith('$'):
                        continue  # Will be resolved from version file
                    hamcrest_info["version"] = version
        
        # Check for variable usage like $hamcrestVersion
        if re.search(r'\$hamcrestVersion', content) and not hamcrest_info["exists"]:
            hamcrest_info["exists"] = True  # Mark as existing if variable is used
    
    def _detect_hamcrest_maven(self, hamcrest_info: Dict[str, Any]) -> Dict[str, Any]:
        """Detect Hamcrest in Maven projects."""
        # Find all pom.xml files
        pom_files = list(self.project_path.glob("**/pom.xml"))
        
        for pom_file in pom_files:
            if '.backup' in str(pom_file) or 'backup' in str(pom_file).lower():
                continue
            
            hamcrest_info["files_checked"].append(str(pom_file))
            try:
                content = pom_file.read_text(encoding='utf-8')
                self._parse_maven_hamcrest(content, hamcrest_info)
            except Exception as e:
                logger.debug(f"Error reading {pom_file}: {e}")
                continue
        
        return hamcrest_info
    
    def _parse_maven_hamcrest(self, content: str, hamcrest_info: Dict[str, Any]):
        """Parse Maven POM content for Hamcrest dependencies."""
        # Look for Hamcrest dependencies in XML
        hamcrest_patterns = [
            (r'<groupId>org\.hamcrest</groupId>\s*<artifactId>hamcrest</artifactId>\s*<version>([^<]+)</version>', "hamcrest"),
            (r'<groupId>org\.hamcrest</groupId>\s*<artifactId>hamcrest-all</artifactId>\s*<version>([^<]+)</version>', "hamcrest-all"),
            (r'<groupId>org\.hamcrest</groupId>\s*<artifactId>hamcrest-core</artifactId>\s*<version>([^<]+)</version>', "hamcrest-core"),
        ]
        
        for pattern, format_type in hamcrest_patterns:
            matches = re.findall(pattern, content, re.DOTALL)
            if matches:
                hamcrest_info["exists"] = True
                hamcrest_info["format"] = format_type
                version = matches[0].strip()
                if not version.startswith('${') and not hamcrest_info["version"]:
                    hamcrest_info["version"] = version
    
    def _is_hamcrest_compatible(self, hamcrest_info: Dict[str, Any]) -> bool:
        """
        Check if existing Hamcrest is compatible with our needs.
        """
        if not hamcrest_info["exists"]:
            return False
        
        version = hamcrest_info["version"]
        format_type = hamcrest_info["format"]
        
        if not version:
            # If we can't determine version, assume it's compatible
            return True
        
        try:
            # Parse version number
            version_parts = version.split('.')
            major = int(version_parts[0])
            minor = int(version_parts[1]) if len(version_parts) > 1 else 0
            
            # Hamcrest 1.3+ or 2.x are generally compatible for basic usage
            if major >= 2:
                return True
            elif major == 1 and minor >= 3:
                return True
            else:
                return False
                
        except (ValueError, IndexError):
            # If we can't parse version, assume compatible
            logger.debug(f"Could not parse Hamcrest version: {version}")
            return True
    
    def add_hamcrest_dependency(self) -> Tuple[bool, str]:
        """Add Hamcrest dependency to the project and ALL submodules."""
        # First, detect existing Hamcrest dependencies
        self.existing_hamcrest_info = self._detect_existing_hamcrest_dependency()
        
        logger.info(f"Hamcrest detection result: {self.existing_hamcrest_info}")
        
        # Check if existing Hamcrest is compatible
        if self.existing_hamcrest_info["exists"]:
            if self._is_hamcrest_compatible(self.existing_hamcrest_info):
                return True, f"Compatible Hamcrest already exists: {self.existing_hamcrest_info['format']}:{self.existing_hamcrest_info['version']}"
            else:
                logger.warning(f"Incompatible Hamcrest version found: {self.existing_hamcrest_info['version']}")
        
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
        # If compatible Hamcrest already exists, don't add new dependencies
        if (self.existing_hamcrest_info and 
            self.existing_hamcrest_info["exists"] and 
            self._is_hamcrest_compatible(self.existing_hamcrest_info)):
            return True, f"Using existing compatible Hamcrest: {self.existing_hamcrest_info['format']}:{self.existing_hamcrest_info['version']}"
        
        # Find all build.gradle and build.gradle.kts files
        gradle_files = []
        
        # Add main build.gradle if it exists
        main_gradle = self.project_path / "build.gradle"
        if main_gradle.exists():
            gradle_files.append(main_gradle)
        
        # Add main build.gradle.kts if it exists
        main_gradle_kts = self.project_path / "build.gradle.kts"
        if main_gradle_kts.exists():
            gradle_files.append(main_gradle_kts)
        
        # Find subproject build files (but skip build output directories)
        for gradle_file in self.project_path.glob("**/build.gradle"):
            if ("build/" in str(gradle_file) or 
                "/.gradle/" in str(gradle_file) or
                gradle_file == main_gradle):
                continue
            gradle_files.append(gradle_file)
            
        for gradle_file in self.project_path.glob("**/build.gradle.kts"):
            if ("build/" in str(gradle_file) or 
                "/.gradle/" in str(gradle_file) or
                gradle_file == main_gradle_kts):
                continue
            gradle_files.append(gradle_file)
        
        if not gradle_files:
            return False, "No build.gradle files found"
        
        logger.info(f"Found {len(gradle_files)} Gradle build files to process")
        
        modified_files = []
        already_present = []
        failed_files = []
        
        # Special handling for projects with existing Hamcrest
        hamcrest_upgrade_strategy = self._determine_hamcrest_upgrade_strategy()
        
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
                
                # Check if modern hamcrest is already present
                if self._is_modern_hamcrest_present_gradle(content):
                    logger.debug(f"  Modern Hamcrest already present in {relative_path}")
                    already_present.append(str(relative_path))
                    continue
                
                # Try to add hamcrest based on the upgrade strategy
                if hamcrest_upgrade_strategy == "skip":
                    logger.debug(f"  Skipping {relative_path} - compatible Hamcrest exists")
                    already_present.append(str(relative_path))
                    continue
                
                modified_content = self._add_to_gradle_dependencies(content, hamcrest_upgrade_strategy)
                
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
    
    def _determine_hamcrest_upgrade_strategy(self) -> str:
        """
        Determine the strategy for adding Hamcrest based on existing dependencies.
        
        Returns:
            "skip" - Don't add, existing is compatible
            "upgrade" - Add modern Hamcrest alongside old
            "add" - Add new Hamcrest dependency
        """
        if not self.existing_hamcrest_info or not self.existing_hamcrest_info["exists"]:
            return "add"
        
        if self._is_hamcrest_compatible(self.existing_hamcrest_info):
            # If existing Hamcrest is compatible but old format, we might want to add modern imports
            if self.existing_hamcrest_info["format"] == "hamcrest-all":
                version = self.existing_hamcrest_info["version"]
                if version and version.startswith("1."):
                    # For Hamcrest 1.x with hamcrest-all, don't add modern version
                    # Instead, we should adapt our import strategy to use 1.x APIs
                    logger.info(f"Found Hamcrest 1.x (hamcrest-all:{version}), will adapt import strategy")
                    return "skip"
            return "skip"
        
        return "upgrade"
    
    def _is_hamcrest_present_maven(self, content: str) -> bool:
        """Check if modern Hamcrest dependency is already present in Maven POM."""
        # Look for Hamcrest 2.x dependency specifically
        hamcrest_patterns = [
            r'<groupId>\s*org\.hamcrest\s*</groupId>\s*<artifactId>\s*hamcrest\s*</artifactId>\s*<version>\s*2\.',
            r'<artifactId>\s*hamcrest\s*</artifactId>\s*<version>\s*2\.',
            r'hamcrest.*?2\.[0-9]',
        ]
        
        for pattern in hamcrest_patterns:
            if re.search(pattern, content, re.IGNORECASE | re.MULTILINE | re.DOTALL):
                return True
        
        # Also check for our marker
        if self.MAVEN_START_MARKER in content:
            return True
            
        return False
    
    def _is_modern_hamcrest_present_gradle(self, content: str) -> bool:
        """Check if modern Hamcrest dependency is already present in Gradle build file."""
        # Look for modern hamcrest:2.x dependency
        modern_patterns = [
            r'hamcrest:2\.[0-9]',
            r'org\.hamcrest.*?hamcrest.*?2\.[0-9]',
            r'AAA-Issue-Refactor.*hamcrest',  # Our marker
        ]
        
        for pattern in modern_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    
    def _insert_hamcrest_maven_minimal(self, content: str) -> str:
        """Insert Hamcrest dependency using minimal string modification."""
        lines = content.split('\n')
        
        # Find the dependencies section
        in_plugin = False
        in_dependencies = False
        dependencies_start = -1
        dependencies_end = -1
        indent = "        "  # Default Maven indent
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Find start of plugin section
            if stripped == '<plugin>' or stripped.startswith('<plugin '):
                in_plugin = True
            
            # Find start of dependencies section
            if not in_plugin and (stripped == '<dependencies>' or stripped.startswith('<dependencies ')):
                in_dependencies = True
                dependencies_start = i
                # Extract indentation from the dependencies tag
                match = re.match(r'^(\s*)', line)
                if match:
                    base_indent = match.group(1)
                    indent = base_indent + "    "  # Add one level of indentation
                continue
            
            # Find end of plugin section
            if in_plugin and stripped == '</plugin>':
                in_plugin = False
            
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
            
            # Look for end of properties
            if stripped == '</properties>':
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
    
    def _add_to_gradle_dependencies(self, content: str, upgrade_strategy: str = "add") -> str:
        """Add Hamcrest to Gradle dependencies block."""
        lines = content.split('\n')
        
        # If upgrading, add modern Hamcrest alongside old
        if upgrade_strategy == "upgrade":
            for i, line in enumerate(lines):
                if ('hamcrest' in line.lower() and 
                    ('testCompile' in line or 'testImplementation' in line or 'testApi' in line) and
                    not 'AAA-Issue-Refactor' in line):
                    
                    # Found existing hamcrest dependency
                    old_line = line
                    # Extract indentation
                    indent_match = re.match(r'^(\s*)', line)
                    indent = indent_match.group(1) if indent_match else "    "
                    
                    # Comment out old line and add new one
                    lines[i] = f'{indent}// {old_line.strip()}  // Commented out by AAA-Issue-Refactor'
                    new_line = f'{indent}testImplementation "org.hamcrest:hamcrest:2.2"  // Added by AAA-Issue-Refactor'
                    lines.insert(i + 1, new_line)
                    logger.debug(f"Upgraded hamcrest dependency to 2.2")
                    return '\n'.join(lines)
        
        # For "add" strategy or if no existing hamcrest found, add new dependency
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
                f"{base_indent}// AAA-Issue-Refactor: Hamcrest dependency",
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