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
    
    # JUnit 5 assumptions
    JUNIT5_ASSUMPTIONS = {
        r'\bAssumptions\.assumeTrue\b': 'org.junit.jupiter.api.Assumptions.assumeTrue',
        r'\bAssumptions\.assumeFalse\b': 'org.junit.jupiter.api.Assumptions.assumeFalse',
        r'\bAssumptions\.assumingThat\b': 'org.junit.jupiter.api.Assumptions.assumingThat',
        r'\bassumeTrue\b': 'org.junit.jupiter.api.Assumptions.assumeTrue',
        r'\bassumeFalse\b': 'org.junit.jupiter.api.Assumptions.assumeFalse',
        r'\bassumingThat\b': 'org.junit.jupiter.api.Assumptions.assumingThat',
    }
    
    # Hamcrest matchers (commonly used patterns)
    HAMCREST_MATCHERS = {
        r'\bassertThat\b': 'org.hamcrest.MatcherAssert.assertThat',
        r'\bis\(' : 'org.hamcrest.Matchers.is',
        r'\bisA\(': 'org.hamcrest.Matchers.isA',
        r'\bequalTo\b': 'org.hamcrest.Matchers.equalTo',
        r'\bnotNullValue\b': 'org.hamcrest.Matchers.notNullValue',
        r'\bnullValue\b': 'org.hamcrest.Matchers.nullValue',
        r'\bhasSize\b': 'org.hamcrest.Matchers.hasSize',
        r'\bhasItem\b': 'org.hamcrest.Matchers.hasItem',
        r'\bhasItems\b': 'org.hamcrest.Matchers.hasItems',
        r'\bcontains\b': 'org.hamcrest.Matchers.contains',
        r'\bcontainsInAnyOrder\b': 'org.hamcrest.Matchers.containsInAnyOrder',
        r'\bempty\b': 'org.hamcrest.Matchers.empty',
        r'\bnot\b': 'org.hamcrest.Matchers.not',
        r'\banyOf\b': 'org.hamcrest.Matchers.anyOf',
        r'\ballOf\b': 'org.hamcrest.Matchers.allOf',
        r'\beveryItem\b': 'org.hamcrest.Matchers.everyItem',
        r'\bgreaterThan\b': 'org.hamcrest.Matchers.greaterThan',
        r'\bgreaterThanOrEqualTo\b': 'org.hamcrest.Matchers.greaterThanOrEqualTo',
        r'\blessThan\b': 'org.hamcrest.Matchers.lessThan',
        r'\blessThanOrEqualTo\b': 'org.hamcrest.Matchers.lessThanOrEqualTo',
        r'\bstartsWith\b': 'org.hamcrest.Matchers.startsWith',
        r'\bendsWith\b': 'org.hamcrest.Matchers.endsWith',
        r'\bcontainsString\b': 'org.hamcrest.Matchers.containsString',
        r'\bisIn\b': 'org.hamcrest.Matchers.isIn',
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
        
        # Check for JUnit assertions
        for pattern, import_class in self.JUNIT5_STATIC_IMPORTS.items():
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
        for pattern, import_class in self.JUNIT5_ASSUMPTIONS.items():
            if re.search(pattern, code):
                if 'Assumptions.' in pattern:
                    # Uses qualified name, need class import
                    class_import = import_class.rsplit('.', 1)[0]
                    if not self._is_import_satisfied(class_import, existing_imports):
                        requirements.append(ImportRequirement(
                            import_statement=class_import,
                            reason=f"Code uses qualified Assumptions",
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
        
        # Check for Hamcrest matchers
        has_hamcrest = False
        for pattern, import_class in self.HAMCREST_MATCHERS.items():
            if re.search(pattern, code):
                static_import = f"static {import_class}"
                pattern_clean = pattern.strip('\\b')
                if not self._is_import_satisfied(static_import, existing_imports):
                    requirements.append(ImportRequirement(
                        import_statement=static_import,
                        reason=f"Code uses Hamcrest matcher {pattern_clean}",
                        priority=2
                    ))
                has_hamcrest = True
        
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
        # Normalize the required import
        if not required_import.startswith('import '):
            required_import = f"import {required_import};"
        elif not required_import.endswith(';'):
            required_import += ';'
        
        # Direct match check
        for existing in existing_imports:
            if self._normalize_import(existing) == self._normalize_import(required_import):
                return True
        
        # For static imports, also check if the class is imported with wildcard
        if 'static' in required_import:
            # Extract class name from static import
            # e.g., "import static org.junit.jupiter.api.Assertions.assertEquals;" -> "org.junit.jupiter.api.Assertions"
            import_parts = required_import.replace('import static ', '').replace(';', '').strip()
            if '.' in import_parts:
                class_name = '.'.join(import_parts.split('.')[:-1])
                wildcard_import = f"import static {class_name}.*;"
                
                for existing in existing_imports:
                    if self._normalize_import(existing) == self._normalize_import(wildcard_import):
                        return True
        
        # For regular class imports, check for wildcard imports
        else:
            # Extract package name
            # e.g., "import java.util.stream.Collectors;" -> "java.util.stream"
            import_content = required_import.replace('import ', '').replace(';', '').strip()
            if '.' in import_content:
                package_name = '.'.join(import_content.split('.')[:-1])
                wildcard_import = f"import {package_name}.*;"
                
                for existing in existing_imports:
                    if self._normalize_import(existing) == self._normalize_import(wildcard_import):
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
        all_imports = set(additional_imports) if additional_imports else set()
        
        # Add auto-detected imports (only those not already satisfied)
        for req in code_requirements:
            all_imports.add(req.import_statement)
            logger.debug(f"Auto-detected import need: {req.import_statement} ({req.reason})")
        
        if not all_imports:
            logger.debug("No new imports needed")
            return content, True
        
        # Filter out imports that already exist (double check for manual imports)
        new_imports = []
        for imp in all_imports:
            # Normalize import statement
            normalized = imp.strip()
            if not normalized.startswith('import '):
                normalized = f"import {normalized};"
            elif not normalized.endswith(';'):
                normalized += ';'
            
            # Check if this import is already satisfied
            if not self._is_import_satisfied(normalized.replace('import ', '').replace(';', ''), existing_imports):
                new_imports.append(normalized)
            else:
                logger.debug(f"Import already satisfied: {normalized}")
        
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
        
        # Insert imports
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