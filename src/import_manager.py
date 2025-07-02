"""Import management for refactored test code."""

import re
import logging
from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger('aif')

@dataclass
class ImportRequirement:
    """Represents an import requirement discovered in code."""
    import_statement: str
    reason: str
    priority: int = 1  # Lower number = higher priority

class SmartImportManager:
    """Manages automatic import resolution for refactored test code."""
    
    # JUnit 5 static imports for common assertion patterns
    JUNIT5_STATIC_IMPORTS = {
        r'\bassertNull\b': 'org.junit.jupiter.api.Assertions.assertNull',
        r'\bassertNotNull\b': 'org.junit.jupiter.api.Assertions.assertNotNull',
        r'\bassertTrue\b': 'org.junit.jupiter.api.Assertions.assertTrue',
        r'\bassertFalse\b': 'org.junit.jupiter.api.Assertions.assertFalse',
        r'\bassertEquals\b': 'org.junit.jupiter.api.Assertions.assertEquals',
        r'\bassertNotEquals\b': 'org.junit.jupiter.api.Assertions.assertNotEquals',
        r'\bassertSame\b': 'org.junit.jupiter.api.Assertions.assertSame',
        r'\bassertNotSame\b': 'org.junit.jupiter.api.Assertions.assertNotSame',
        r'\bassertThrows\b': 'org.junit.jupiter.api.Assertions.assertThrows',
        r'\bassertDoesNotThrow\b': 'org.junit.jupiter.api.Assertions.assertDoesNotThrow',
        r'\bassertTimeout\b': 'org.junit.jupiter.api.Assertions.assertTimeout',
        r'\bassertTimeoutPreemptively\b': 'org.junit.jupiter.api.Assertions.assertTimeoutPreemptively',
        r'\bassertArrayEquals\b': 'org.junit.jupiter.api.Assertions.assertArrayEquals',
        r'\bassertIterableEquals\b': 'org.junit.jupiter.api.Assertions.assertIterableEquals',
        r'\bassertLinesMatch\b': 'org.junit.jupiter.api.Assertions.assertLinesMatch',
        r'\bassertAll\b': 'org.junit.jupiter.api.Assertions.assertAll',
        r'\bfail\b': 'org.junit.jupiter.api.Assertions.fail',
    }
    
    # JUnit 4 static imports for backward compatibility
    JUNIT4_STATIC_IMPORTS = {
        r'\bassertNull\b': 'org.junit.Assert.assertNull',
        r'\bassertNotNull\b': 'org.junit.Assert.assertNotNull',
        r'\bassertTrue\b': 'org.junit.Assert.assertTrue',
        r'\bassertFalse\b': 'org.junit.Assert.assertFalse',
        r'\bassertEquals\b': 'org.junit.Assert.assertEquals',
        r'\bassertNotEquals\b': 'org.junit.Assert.assertNotEquals',
        r'\bassertSame\b': 'org.junit.Assert.assertSame',
        r'\bassertNotSame\b': 'org.junit.Assert.assertNotSame',
        r'\bassertArrayEquals\b': 'org.junit.Assert.assertArrayEquals',
        r'\bfail\b': 'org.junit.Assert.fail',
    }
    
    # JUnit 5 assumptions
    JUNIT5_ASSUMPTIONS = {
        r'\bAssumptions\.assumeTrue\b': 'org.junit.jupiter.api.Assumptions.assumeTrue',
        r'\bAssumptions\.assumeFalse\b': 'org.junit.jupiter.api.Assumptions.assumeFalse',
        r'\bAssumptions\.assumingThat\b': 'org.junit.jupiter.api.Assumptions.assumingThat',
        r'\bassumeTrue\b': 'org.junit.jupiter.api.Assumptions.assumeTrue',
        r'\bassumeFalse\b': 'org.junit.jupiter.api.Assumptions.assumeFalse',
        r'\bassumingThat\b': 'org.junit.jupiter.api.Assumptions.assumingThat',
    }
    
    # JUnit 4 assumptions for backward compatibility
    JUNIT4_ASSUMPTIONS = {
        r'\bAssume\.assumeTrue\b': 'org.junit.Assume.assumeTrue',
        r'\bAssume\.assumeFalse\b': 'org.junit.Assume.assumeFalse',
        r'\bAssume\.assumeNotNull\b': 'org.junit.Assume.assumeNotNull',
        r'\bAssume\.assumeNoException\b': 'org.junit.Assume.assumeNoException',
        r'\bAssume\.assumeThat\b': 'org.junit.Assume.assumeThat',
    }
    
    # Hamcrest matchers (using org.hamcrest.Matchers for Hamcrest 2.x)
    # Note: In Hamcrest 2.x+, org.hamcrest.Matchers does exist and should be used
    HAMCREST_MATCHERS = {
        r'\bassertThat\s*\(': 'org.hamcrest.MatcherAssert.assertThat',
        r'\bis\s*\(' : 'org.hamcrest.Matchers.is',
        r'\bisA\s*\(': 'org.hamcrest.Matchers.isA',
        r'\bequalTo\s*\(': 'org.hamcrest.Matchers.equalTo',
        r'\bnotNullValue\s*\(': 'org.hamcrest.Matchers.notNullValue',
        r'\bnullValue\s*\(': 'org.hamcrest.Matchers.nullValue',
        r'\bhasSize\s*\(': 'org.hamcrest.Matchers.hasSize',
        r'\bhasItem\s*\(': 'org.hamcrest.Matchers.hasItem',
        r'\bhasItems\s*\(': 'org.hamcrest.Matchers.hasItems',
        r'\bcontains\s*\(': 'org.hamcrest.Matchers.contains',
        r'\bcontainsInAnyOrder\s*\(': 'org.hamcrest.Matchers.containsInAnyOrder',
        r'\bempty\s*\(': 'org.hamcrest.Matchers.empty',
        r'\bnot\s*\(': 'org.hamcrest.Matchers.not',
        r'\banyOf\s*\(': 'org.hamcrest.Matchers.anyOf',
        r'\ballOf\s*\(': 'org.hamcrest.Matchers.allOf',
        r'\beveryItem\s*\(': 'org.hamcrest.Matchers.everyItem',
        r'\bgreaterThan\s*\(': 'org.hamcrest.Matchers.greaterThan',
        r'\bgreaterThanOrEqualTo\s*\(': 'org.hamcrest.Matchers.greaterThanOrEqualTo',
        r'\blessThan\s*\(': 'org.hamcrest.Matchers.lessThan',
        r'\blessThanOrEqualTo\s*\(': 'org.hamcrest.Matchers.lessThanOrEqualTo',
        r'\bstartsWith\s*\(': 'org.hamcrest.Matchers.startsWith',
        r'\bendsWith\s*\(': 'org.hamcrest.Matchers.endsWith',
        r'\bcontainsString\s*\(': 'org.hamcrest.Matchers.containsString',
        r'\bisIn\s*\(': 'org.hamcrest.Matchers.isIn',
        r'\bhasEntry\s*\(': 'org.hamcrest.Matchers.hasEntry',
        r'\bhasKey\s*\(': 'org.hamcrest.Matchers.hasKey',
        r'\bhasProperty\s*\(': 'org.hamcrest.Matchers.hasProperty',
        r'\bhasValue\s*\(': 'org.hamcrest.Matchers.hasValue',
        r'\binstanceOf\s*\(': 'org.hamcrest.Matchers.instanceOf',
        r'\btypeCompatibleWith\s*\(': 'org.hamcrest.Matchers.typeCompatibleWith',
    }
    
    # Alternative Hamcrest CoreMatchers (fallback for older versions)
    HAMCREST_CORE_MATCHERS = {
        r'\bis\s*\(' : 'org.hamcrest.CoreMatchers.is',
        r'\bequalTo\s*\(': 'org.hamcrest.CoreMatchers.equalTo',
        r'\bnotNullValue\s*\(': 'org.hamcrest.CoreMatchers.notNullValue',
        r'\bnullValue\s*\(': 'org.hamcrest.CoreMatchers.nullValue',
        r'\bnot\s*\(': 'org.hamcrest.CoreMatchers.not',
        r'\banyOf\s*\(': 'org.hamcrest.CoreMatchers.anyOf',
        r'\ballOf\s*\(': 'org.hamcrest.CoreMatchers.allOf',
        r'\bstartsWith\s*\(': 'org.hamcrest.CoreMatchers.startsWith',
        r'\bendsWith\s*\(': 'org.hamcrest.CoreMatchers.endsWith',
        r'\bcontainsString\s*\(': 'org.hamcrest.CoreMatchers.containsString',
        r'\binstanceOf\s*\(': 'org.hamcrest.CoreMatchers.instanceOf',
    }
    
    # Java utility imports for common stream operations
    JAVA_UTIL_IMPORTS = {
        r'\bCollectors\.': 'java.util.stream.Collectors',
        r'\bStream\.': 'java.util.stream.Stream',
        r'\bArrays\.': 'java.util.Arrays',
        r'\bCollections\.': 'java.util.Collections',
        r'\bOptional\.': 'java.util.Optional',
    }
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.junit_version = self._detect_junit_version()
        self.hamcrest_version = self._detect_hamcrest_version()
        logger.debug(f"Detected JUnit {self.junit_version}, Hamcrest {self.hamcrest_version}")
        
    def _detect_junit_version(self) -> str:
        """Detect JUnit version used in the project."""
        # Check pom.xml for Maven projects
        pom_file = self.project_path / "pom.xml"
        if pom_file.exists():
            try:
                content = pom_file.read_text(encoding='utf-8')
                if 'junit-jupiter' in content or 'org.junit.jupiter' in content:
                    return "5"
                elif 'junit' in content and ('4.' in content or 'org.junit' in content):
                    return "4"
            except Exception:
                pass
        
        # Check build.gradle for Gradle projects  
        gradle_files = list(self.project_path.glob("**/build.gradle*"))
        for gradle_file in gradle_files:
            try:
                content = gradle_file.read_text(encoding='utf-8')
                if 'junit-jupiter' in content or 'org.junit.jupiter' in content:
                    return "5"
                elif 'junit' in content and ('4.' in content or 'org.junit' in content):
                    return "4"
            except Exception:
                pass
        
        # Default to JUnit 5 for modern projects
        logger.debug("Could not detect JUnit version, defaulting to JUnit 5")
        return "5"
    
    def _detect_hamcrest_version(self) -> str:
        """Detect Hamcrest version used in the project."""
        # Check for Maven
        pom_file = self.project_path / "pom.xml"
        if pom_file.exists():
            try:
                content = pom_file.read_text(encoding='utf-8')
                if 'hamcrest' in content:
                    # Look for version patterns
                    if '2.2' in content or '2.1' in content or '2.0' in content:
                        return "2.x"
                    elif '1.' in content:
                        return "1.x"
            except Exception:
                pass
        
        # Check for Gradle
        gradle_files = list(self.project_path.glob("**/build.gradle*"))
        for gradle_file in gradle_files:
            try:
                content = gradle_file.read_text(encoding='utf-8')
                if 'hamcrest' in content:
                    if '2.2' in content or '2.1' in content or '2.0' in content:
                        return "2.x"
                    elif '1.' in content:
                        return "1.x"
            except Exception:
                pass
        
        # Default to 2.x since that's what we're adding
        return "2.x"
    
    def analyze_code_requirements(self, code: str, existing_imports: Optional[Set[str]] = None) -> List[ImportRequirement]:
        """
        Analyze code and determine required imports, considering existing imports.
        
        Args:
            code: The code to analyze
            existing_imports: Set of existing import statements in the file
            
        Returns:
            List of import requirements that are not already satisfied
        """
        requirements = []
        existing_imports = existing_imports or set()
        
        # Select appropriate JUnit imports based on version
        if self.junit_version == "5":
            junit_imports = self.JUNIT5_STATIC_IMPORTS
            junit_assumptions = self.JUNIT5_ASSUMPTIONS
        else:
            junit_imports = self.JUNIT4_STATIC_IMPORTS
            junit_assumptions = self.JUNIT4_ASSUMPTIONS
        
        # Check for JUnit assertions
        for pattern, import_class in junit_imports.items():
            if re.search(pattern, code):
                static_import = f"static {import_class}"
                pattern_clean = pattern.strip('\\b')
                
                # Check if this import is already satisfied
                if not self._is_import_satisfied(static_import, existing_imports):
                    requirements.append(ImportRequirement(
                        import_statement=static_import,
                        reason=f"Code uses {pattern_clean} assertion",
                        priority=1
                    ))
        
        # Check for JUnit assumptions
        for pattern, import_class in junit_assumptions.items():
            if re.search(pattern, code):
                if 'Assumptions.' in pattern or 'Assume.' in pattern:
                    # Uses qualified name, need class import
                    class_import = import_class.rsplit('.', 1)[0]
                    if not self._is_import_satisfied(class_import, existing_imports):
                        requirements.append(ImportRequirement(
                            import_statement=class_import,
                            reason=f"Code uses qualified {class_import.split('.')[-1]}",
                            priority=1
                        ))
                else:
                    # Uses static import
                    static_import = f"static {import_class}"
                    pattern_clean = pattern.strip('\\b')
                    if not self._is_import_satisfied(static_import, existing_imports):
                        requirements.append(ImportRequirement(
                            import_statement=static_import,
                            reason=f"Code uses {pattern_clean} assumption",
                            priority=1
                        ))
        
        # Check for Hamcrest matchers (prefer Matchers over CoreMatchers for 2.x)
        hamcrest_matchers = self.HAMCREST_MATCHERS if self.hamcrest_version == "2.x" else self.HAMCREST_CORE_MATCHERS
        
        for pattern, import_class in hamcrest_matchers.items():
            if re.search(pattern, code):
                static_import = f"static {import_class}"
                pattern_clean = pattern.strip('\\b').strip('\\s*\\(')
                if not self._is_import_satisfied(static_import, existing_imports):
                    requirements.append(ImportRequirement(
                        import_statement=static_import,
                        reason=f"Code uses Hamcrest matcher {pattern_clean}",
                        priority=2
                    ))
        
        # Check for Java utility imports
        for pattern, import_class in self.JAVA_UTIL_IMPORTS.items():
            if re.search(pattern, code):
                if not self._is_import_satisfied(import_class, existing_imports):
                    requirements.append(ImportRequirement(
                        import_statement=import_class,
                        reason=f"Code uses {import_class.split('.')[-1]} utility",
                        priority=3
                    ))
        
        # Remove duplicates and sort by priority
        unique_requirements = {}
        for req in requirements:
            if req.import_statement not in unique_requirements:
                unique_requirements[req.import_statement] = req
        
        return sorted(unique_requirements.values(), key=lambda x: x.priority)
    
    def _is_import_satisfied(self, required_import: str, existing_imports: Set[str]) -> bool:
        """
        Check if a required import is already satisfied by existing imports.
        
        Args:
            required_import: The import we need (e.g., "static org.junit.jupiter.api.Assertions.assertEquals")
            existing_imports: Set of existing import statements
            
        Returns:
            True if the import is already satisfied
        """
        # Normalize the required import to include import prefix
        normalized_required = required_import
        if not normalized_required.startswith('import '):
            normalized_required = f"import {normalized_required};"
        elif not normalized_required.endswith(';'):
            normalized_required += ';'
        
        # Direct match check
        for existing in existing_imports:
            existing_normalized = existing
            if not existing_normalized.startswith('import '):
                existing_normalized = f"import {existing_normalized};"
            elif not existing_normalized.endswith(';'):
                existing_normalized += ';'
                
            if self._normalize_import(existing_normalized) == self._normalize_import(normalized_required):
                return True
        
        # For static imports, also check if the class is imported with wildcard
        if 'static' in normalized_required:
            # Extract class name from static import
            # e.g., "import static org.junit.jupiter.api.Assertions.assertEquals;" -> "org.junit.jupiter.api.Assertions"
            import_parts = normalized_required.replace('import static ', '').replace(';', '').strip()
            if '.' in import_parts:
                class_name = '.'.join(import_parts.split('.')[:-1])
                wildcard_import = f"import static {class_name}.*;"
                
                for existing in existing_imports:
                    existing_normalized = existing
                    if not existing_normalized.startswith('import '):
                        existing_normalized = f"import {existing_normalized};"
                    elif not existing_normalized.endswith(';'):
                        existing_normalized += ';'
                        
                    if self._normalize_import(existing_normalized) == self._normalize_import(wildcard_import):
                        return True
        
        # For regular class imports, check for wildcard imports
        else:
            # Extract package name
            # e.g., "import java.util.stream.Collectors;" -> "java.util.stream"
            import_content = normalized_required.replace('import ', '').replace(';', '').strip()
            if '.' in import_content:
                package_name = '.'.join(import_content.split('.')[:-1])
                wildcard_import = f"import {package_name}.*;"
                
                for existing in existing_imports:
                    existing_normalized = existing
                    if not existing_normalized.startswith('import '):
                        existing_normalized = f"import {existing_normalized};"
                    elif not existing_normalized.endswith(';'):
                        existing_normalized += ';'
                        
                    if self._normalize_import(existing_normalized) == self._normalize_import(wildcard_import):
                        return True
        
        return False
    
    def _normalize_import(self, import_statement: str) -> str:
        """Normalize import statement for comparison."""
        return import_statement.replace(' ', '').replace('\t', '').lower()
    
    def extract_existing_imports(self, content: str) -> Set[str]:
        """Extract existing import statements from Java file content."""
        imports = set()
        
        # Match both regular and static imports
        import_pattern = r'^import\s+(?:static\s+)?([^;]+);'
        for line in content.split('\n'):
            match = re.match(import_pattern, line.strip())
            if match:
                imports.add(line.strip())
        
        return imports
    
    def add_missing_imports(self, content: str, additional_imports: List[str]) -> Tuple[str, bool]:
        """
        Enhanced import adding that automatically detects and adds missing imports.
        
        Args:
            content: Original Java file content
            additional_imports: List of manually specified imports
            
        Returns:
            Tuple of (modified_content, success)
        """
        # Get existing imports first
        existing_imports = self.extract_existing_imports(content)
        
        # Analyze code to find required imports, considering existing ones
        code_requirements = self.analyze_code_requirements(content, existing_imports)
        
        # Combine manual imports with auto-detected ones
        all_imports = set()
        
        # Process manual imports first (clean format)
        if additional_imports:
            for imp in additional_imports:
                cleaned = imp.strip()
                # Remove any 'import ' prefix and ';' suffix for consistency
                if cleaned.startswith('import '):
                    cleaned = cleaned[7:]  # Remove 'import '
                if cleaned.endswith(';'):
                    cleaned = cleaned[:-1]  # Remove ';'
                all_imports.add(cleaned)
        
        # Add auto-detected imports (these come without 'import ' prefix)
        for req in code_requirements:
            import_statement = req.import_statement
            # Remove 'import ' prefix if present for consistency
            if import_statement.startswith('import '):
                import_statement = import_statement[7:]
            if import_statement.endswith(';'):
                import_statement = import_statement[:-1]
            all_imports.add(import_statement)
            logger.debug(f"Auto-detected import need: {import_statement} ({req.reason})")
        
        if not all_imports:
            logger.debug("No new imports needed")
            return content, True
        
        # Filter out imports that already exist
        new_imports = []
        for imp in all_imports:
            # Check if this import is already satisfied
            if not self._is_import_satisfied(imp, existing_imports):
                # Format as proper import statement
                formatted_import = f"import {imp};"
                new_imports.append(formatted_import)
            else:
                logger.debug(f"Import already satisfied: {imp}")
        
        if not new_imports:
            logger.debug("All required imports already exist or are satisfied")
            return content, True
        
        return self._insert_imports(content, new_imports)
    
    def _insert_imports(self, content: str, new_imports: List[str]) -> Tuple[str, bool]:
        """Insert new import statements at the appropriate location."""
        lines = content.split('\n')
        
        # Find insertion point
        insertion_point = self._find_import_insertion_point(lines)
        
        if insertion_point == -1:
            logger.warning("Could not find appropriate insertion point for imports")
            return content, False
        
        # Sort imports: static imports first, then regular imports, both alphabetically
        static_imports = [imp for imp in new_imports if 'static' in imp]
        regular_imports = [imp for imp in new_imports if 'static' not in imp]
        
        static_imports.sort()
        regular_imports.sort()
        
        # Insert imports (reverse order because we're inserting at the same point)
        for imp in reversed(regular_imports + static_imports):
            lines.insert(insertion_point, imp)
            logger.debug(f"Added import: {imp}")
        
        return '\n'.join(lines), True
    
    def _find_import_insertion_point(self, lines: List[str]) -> int:
        """Find the best place to insert new import statements."""
        last_import_line = -1
        package_line = -1
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("package "):
                package_line = i
            elif stripped.startswith("import "):
                last_import_line = i
        
        # Insert after last existing import
        if last_import_line != -1:
            return last_import_line + 1
        
        # Insert after package declaration
        if package_line != -1:
            # Look for first non-comment line after package
            for i in range(package_line + 1, len(lines)):
                stripped = lines[i].strip()
                if stripped and not stripped.startswith("//") and not stripped.startswith("/*"):
                    return i
            return package_line + 1
        
        # Fallback: insert at the beginning (after any leading comments)
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("//") and not stripped.startswith("/*") and not stripped.startswith("*"):
                return i
        
        return 0

    def check_hamcrest_dependency(self, code: str) -> bool:
        """Check if code uses Hamcrest and whether dependency might be needed."""
        for pattern in self.HAMCREST_MATCHERS.keys():
            if re.search(pattern, code):
                return True
        return False

    def suggest_dependency_additions(self, code: str) -> List[Dict[str, str]]:
        """Suggest dependency additions that might be needed for the refactored code."""
        suggestions = []
        
        if self.check_hamcrest_dependency(code):
            suggestions.append({
                'type': 'hamcrest',
                'maven': '''<dependency>
    <groupId>org.hamcrest</groupId>
    <artifactId>hamcrest</artifactId>
    <version>2.2</version>
    <scope>test</scope>
</dependency>''',
                'gradle': "testImplementation 'org.hamcrest:hamcrest:2.2'",
                'reason': 'Code uses Hamcrest matchers for assertions'
            })
        
        return suggestions 