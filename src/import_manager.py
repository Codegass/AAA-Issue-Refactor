"""Import management for refactored test code."""

import re
import logging
from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple, Any
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
        r'\bassertNull\s*\(': 'org.junit.jupiter.api.Assertions.assertNull',
        r'\bassertNotNull\s*\(': 'org.junit.jupiter.api.Assertions.assertNotNull',
        r'\bassertTrue\s*\(': 'org.junit.jupiter.api.Assertions.assertTrue',
        r'\bassertFalse\s*\(': 'org.junit.jupiter.api.Assertions.assertFalse',
        r'\bassertEquals\s*\(': 'org.junit.jupiter.api.Assertions.assertEquals',
        r'\bassertNotEquals\s*\(': 'org.junit.jupiter.api.Assertions.assertNotEquals',
        r'\bassertSame\s*\(': 'org.junit.jupiter.api.Assertions.assertSame',
        r'\bassertNotSame\s*\(': 'org.junit.jupiter.api.Assertions.assertNotSame',
        r'\bassertThrows\s*\(': 'org.junit.jupiter.api.Assertions.assertThrows',
        r'\bassertDoesNotThrow\s*\(': 'org.junit.jupiter.api.Assertions.assertDoesNotThrow',
        r'\bassertTimeout\s*\(': 'org.junit.jupiter.api.Assertions.assertTimeout',
        r'\bassertTimeoutPreemptively\s*\(': 'org.junit.jupiter.api.Assertions.assertTimeoutPreemptively',
        r'\bassertArrayEquals\s*\(': 'org.junit.jupiter.api.Assertions.assertArrayEquals',
        r'\bassertIterableEquals\s*\(': 'org.junit.jupiter.api.Assertions.assertIterableEquals',
        r'\bassertLinesMatch\s*\(': 'org.junit.jupiter.api.Assertions.assertLinesMatch',
        r'\bassertAll\s*\(': 'org.junit.jupiter.api.Assertions.assertAll',
        r'\bfail\s*\(': 'org.junit.jupiter.api.Assertions.fail',
    }
    
    # JUnit 4 static imports for backward compatibility
    JUNIT4_STATIC_IMPORTS = {
        r'\bassertNull\s*\(': 'org.junit.Assert.assertNull',
        r'\bassertNotNull\s*\(': 'org.junit.Assert.assertNotNull',
        r'\bassertTrue\s*\(': 'org.junit.Assert.assertTrue',
        r'\bassertFalse\s*\(': 'org.junit.Assert.assertFalse',
        r'\bassertEquals\s*\(': 'org.junit.Assert.assertEquals',
        r'\bassertNotEquals\s*\(': 'org.junit.Assert.assertNotEquals',
        r'\bassertSame\s*\(': 'org.junit.Assert.assertSame',
        r'\bassertNotSame\s*\(': 'org.junit.Assert.assertNotSame',
        r'\bassertArrayEquals\s*\(': 'org.junit.Assert.assertArrayEquals',
        r'\bfail\s*\(': 'org.junit.Assert.fail',
    }
    
    # JUnit 5 assumptions
    JUNIT5_ASSUMPTIONS = {
        r'\bAssumptions\.assumeTrue\s*\(': 'org.junit.jupiter.api.Assumptions.assumeTrue',
        r'\bAssumptions\.assumeFalse\s*\(': 'org.junit.jupiter.api.Assumptions.assumeFalse',
        r'\bAssumptions\.assumingThat\s*\(': 'org.junit.jupiter.api.Assumptions.assumingThat',
        r'\bassumeTrue\s*\(': 'org.junit.jupiter.api.Assumptions.assumeTrue',
        r'\bassumeFalse\s*\(': 'org.junit.jupiter.api.Assumptions.assumeFalse',
        r'\bassumingThat\s*\(': 'org.junit.jupiter.api.Assumptions.assumingThat',
    }
    
    # JUnit 4 assumptions for backward compatibility
    JUNIT4_ASSUMPTIONS = {
        r'\bAssume\.assumeTrue\s*\(': 'org.junit.Assume.assumeTrue',
        r'\bAssume\.assumeFalse\s*\(': 'org.junit.Assume.assumeFalse',
        r'\bAssume\.assumeNotNull\s*\(': 'org.junit.Assume.assumeNotNull',
        r'\bAssume\.assumeNoException\s*\(': 'org.junit.Assume.assumeNoException',
        r'\bAssume\.assumeThat\s*\(': 'org.junit.Assume.assumeThat',
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
        self.dependency_info = self._get_dependency_info()
        self.junit_version = self._detect_junit_version()
        self.hamcrest_version = self._detect_hamcrest_version()
        logger.debug(f"Detected JUnit {self.junit_version}, Hamcrest {self.hamcrest_version}")
        logger.debug(f"Dependency info: {self.dependency_info}")
    
    def _get_dependency_info(self) -> Dict[str, Any]:
        """Get comprehensive dependency information from DependencyManager."""
        try:
            from .dependency_manager import DependencyManager
            dm = DependencyManager(self.project_path)
            return dm._detect_existing_hamcrest_dependency()
        except Exception as e:
            logger.debug(f"Could not get dependency info: {e}")
            return {"exists": False, "version": None, "format": None}
        
    def _detect_junit_version(self) -> str:
        """Enhanced JUnit version detection with more accurate patterns."""
        junit_version = None
        
        # Check for specific JUnit version declarations
        gradle_files = [self.project_path / "build.gradle"] + list(self.project_path.glob("**/build.gradle*"))
        dependency_files = [
            self.project_path / "gradle" / "dependency-versions.gradle",
            self.project_path / "gradle.properties"
        ]
        
        # Check all Gradle-related files
        all_files = gradle_files + dependency_files + [self.project_path / "pom.xml"]
        
        for file_path in all_files:
            if not file_path.exists() or "build/" in str(file_path):
                continue
                
            try:
                content = file_path.read_text(encoding='utf-8')
                
                # Look for explicit JUnit version declarations
                junit5_patterns = [
                    r'junit-jupiter',
                    r'org\.junit\.jupiter',
                    r'junitVersion\s*=\s*["\']5\.',
                    r'junit.*5\.\d',
                    r'@TestMethodOrder',  # JUnit 5 specific annotation
                    r'@ParameterizedTest'  # JUnit 5 specific annotation
                ]
                
                junit4_patterns = [
                    r'junitVersion\s*=\s*["\']4\.',
                    r'junit.*4\.\d',
                    r'org\.junit\.Test',  # JUnit 4 Test import
                    r'@RunWith',  # JUnit 4 specific (though can appear in 5 with vintage)
                    r'junit:junit:4'
                ]
                
                # Check for JUnit 5 patterns
                for pattern in junit5_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        junit_version = "5"
                        break
                
                # If not found, check for JUnit 4 patterns
                if not junit_version:
                    for pattern in junit4_patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            junit_version = "4"
                            break
                
                if junit_version:
                    logger.debug(f"Detected JUnit {junit_version} from {file_path}")
                    break
                    
            except Exception as e:
                logger.debug(f"Error reading {file_path}: {e}")
                continue
        
        # Enhanced heuristic based on existing test code patterns
        if not junit_version:
            junit_version = self._detect_junit_from_test_code()
        
        # Final fallback: default to JUnit 4 for older projects with hamcrest-all
        if not junit_version:
            if (self.dependency_info.get("format") == "hamcrest-all" and 
                self.dependency_info.get("version", "").startswith("1.")):
                logger.debug("Defaulting to JUnit 4 based on hamcrest-all:1.x presence")
                return "4"
            else:
                logger.debug("Could not detect JUnit version, defaulting to JUnit 4 for safety")
                return "4"  # Changed default to 4 for better compatibility
        
        return junit_version
    
    def _detect_junit_from_test_code(self) -> Optional[str]:
        """Detect JUnit version from actual test code patterns."""
        try:
            # Look for test files in the project
            test_files = list(self.project_path.glob("**/src/test/**/*.java"))
            
            junit5_indicators = 0
            junit4_indicators = 0
            
            for test_file in test_files[:10]:  # Sample first 10 test files
                try:
                    content = test_file.read_text(encoding='utf-8')
                    
                    # JUnit 5 indicators
                    if 'org.junit.jupiter' in content:
                        junit5_indicators += 3
                    if '@TestMethodOrder' in content or '@ParameterizedTest' in content:
                        junit5_indicators += 2
                    if 'assertThrows(' in content or 'assertDoesNotThrow(' in content:
                        junit5_indicators += 1
                    
                    # JUnit 4 indicators
                    if 'org.junit.Test' in content and 'org.junit.jupiter' not in content:
                        junit4_indicators += 3
                    if '@RunWith(' in content:
                        junit4_indicators += 2
                    if 'org.junit.Assert' in content:
                        junit4_indicators += 1
                        
                except Exception:
                    continue
            
            if junit5_indicators > junit4_indicators:
                return "5"
            elif junit4_indicators > 0:
                return "4"
                
        except Exception as e:
            logger.debug(f"Error detecting JUnit from test code: {e}")
        
        return None
        
    def _detect_hamcrest_version(self) -> str:
        """Enhanced Hamcrest version detection using DependencyManager results."""
        # Use DependencyManager results if available
        if self.dependency_info.get("exists"):
            version = self.dependency_info.get("version")
            format_type = self.dependency_info.get("format")
            
            if format_type == "hamcrest-all":
                return "1.x"  # hamcrest-all is always 1.x format
            elif format_type in ["hamcrest", "hamcrest-core"]:
                if version:
                    if version.startswith("2."):
                        return "2.x"
                    elif version.startswith("1."):
                        return "1.x"
            
            # Fallback based on format
            if format_type:
                return "1.x" if format_type.endswith("-all") else "2.x"
        
        # Fallback to original detection logic
        for file_path in [self.project_path / "pom.xml"] + list(self.project_path.glob("**/build.gradle*")):
            if not file_path.exists() or "build/" in str(file_path):
                continue
                
            try:
                content = file_path.read_text(encoding='utf-8')
                if 'hamcrest' in content:
                    if '2.2' in content or '2.1' in content or '2.0' in content:
                        return "2.x"
                    elif '1.' in content or 'hamcrest-all' in content:
                        return "1.x"
            except Exception:
                pass
        
        # Default based on our dependency info
        return "1.x" if self.dependency_info.get("format") == "hamcrest-all" else "2.x"
    
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
        
        # CRITICAL: Detect JUnit version conflicts in existing imports
        junit_conflict_info = self._detect_junit_version_conflicts(existing_imports)
        
        # Select appropriate JUnit imports based on version and conflict detection
        if junit_conflict_info['has_conflict']:
            # In case of conflict, prioritize the detected project version but warn user
            logger.warning(f"JUnit version conflict detected in existing imports!")
            logger.warning(f"Project JUnit version: {self.junit_version}")
            logger.warning(f"Existing JUnit 4 imports: {junit_conflict_info['junit4_imports']}")
            logger.warning(f"Existing JUnit 5 imports: {junit_conflict_info['junit5_imports']}")
            
            # Use the project's detected version but add a warning comment to imports
            if self.junit_version == "5":
                junit_imports = self.JUNIT5_STATIC_IMPORTS
                junit_assumptions = self.JUNIT5_ASSUMPTIONS
                logger.warning("Using JUnit 5 imports to match project configuration. Consider removing JUnit 4 imports.")
            else:
                junit_imports = self.JUNIT4_STATIC_IMPORTS
                junit_assumptions = self.JUNIT4_ASSUMPTIONS
                logger.warning("Using JUnit 4 imports to match project configuration. Consider upgrading to JUnit 5.")
        else:
            # No conflict detected, use normal logic
            if junit_conflict_info['existing_junit_version']:
                # Use the version found in existing imports (more reliable than project detection)
                if junit_conflict_info['existing_junit_version'] == "5":
                    junit_imports = self.JUNIT5_STATIC_IMPORTS
                    junit_assumptions = self.JUNIT5_ASSUMPTIONS
                    logger.debug("Using JUnit 5 imports based on existing imports")
                else:
                    junit_imports = self.JUNIT4_STATIC_IMPORTS
                    junit_assumptions = self.JUNIT4_ASSUMPTIONS
                    logger.debug("Using JUnit 4 imports based on existing imports")
            else:
                # Fall back to project detection
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
                
                # Check if this import is already satisfied or conflicts
                if not self._is_import_satisfied(static_import, existing_imports):
                    # Additional check: avoid adding conflicting JUnit versions
                    if not self._would_create_junit_conflict(static_import, existing_imports):
                        requirements.append(ImportRequirement(
                            import_statement=static_import,
                            reason=f"Code uses {pattern_clean} assertion",
                            priority=1
                        ))
                    else:
                        logger.warning(f"Skipping {static_import} to avoid JUnit version conflict")
        
        # Check for JUnit assumptions
        for pattern, import_class in junit_assumptions.items():
            if re.search(pattern, code):
                if 'Assumptions.' in pattern or 'Assume.' in pattern:
                    # Uses qualified name, need class import
                    class_import = import_class.rsplit('.', 1)[0]
                    if not self._is_import_satisfied(class_import, existing_imports):
                        if not self._would_create_junit_conflict(class_import, existing_imports):
                            requirements.append(ImportRequirement(
                                import_statement=class_import,
                                reason=f"Code uses qualified {class_import.split('.')[-1]}",
                                priority=1
                            ))
                        else:
                            logger.warning(f"Skipping {class_import} to avoid JUnit version conflict")
                else:
                    # Uses static import
                    static_import = f"static {import_class}"
                    pattern_clean = pattern.strip('\\b')
                    if not self._is_import_satisfied(static_import, existing_imports):
                        if not self._would_create_junit_conflict(static_import, existing_imports):
                            requirements.append(ImportRequirement(
                                import_statement=static_import,
                                reason=f"Code uses {pattern_clean} assumption",
                                priority=1
                            ))
                        else:
                            logger.warning(f"Skipping {static_import} to avoid JUnit version conflict")
        
        # Check for Hamcrest matchers with version-specific handling
        hamcrest_requirements = self._analyze_hamcrest_requirements(code, existing_imports)
        requirements.extend(hamcrest_requirements)
        
        # Check for Mockito static imports (fix the static import format issue)
        mockito_requirements = self._analyze_mockito_requirements(code, existing_imports)
        requirements.extend(mockito_requirements)
        
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
    
    def _detect_junit_version_conflicts(self, existing_imports: Set[str]) -> Dict[str, Any]:
        """
        Detect JUnit version conflicts in existing imports.
        
        Returns:
            Dictionary with conflict information
        """
        junit4_imports = []
        junit5_imports = []
        
        for import_stmt in existing_imports:
            # Clean up the import statement for analysis
            clean_import = import_stmt.replace('import ', '').replace('static ', '').replace(';', '').strip()
            
            if 'org.junit.jupiter' in clean_import:
                junit5_imports.append(import_stmt)
            elif ('org.junit.Test' in clean_import or 
                  'org.junit.Assert' in clean_import or 
                  'org.junit.Before' in clean_import or 
                  'org.junit.After' in clean_import or
                  'org.junit.Assume' in clean_import or
                  'org.junit.Rule' in clean_import):
                # Only count as JUnit 4 if it's not Jupiter (to avoid false positives)
                if 'jupiter' not in clean_import:
                    junit4_imports.append(import_stmt)
        
        has_conflict = len(junit4_imports) > 0 and len(junit5_imports) > 0
        
        # Determine existing JUnit version based on imports (most reliable)
        existing_junit_version = None
        if junit5_imports and not junit4_imports:
            existing_junit_version = "5"
        elif junit4_imports and not junit5_imports:
            existing_junit_version = "4"
        # If both exist, we have a conflict, don't set a version
        
        return {
            'has_conflict': has_conflict,
            'junit4_imports': junit4_imports,
            'junit5_imports': junit5_imports,
            'existing_junit_version': existing_junit_version
        }
    
    def _would_create_junit_conflict(self, proposed_import: str, existing_imports: Set[str]) -> bool:
        """
        Check if adding the proposed import would create a JUnit version conflict.
        
        Args:
            proposed_import: The import we want to add
            existing_imports: Current imports in the file
            
        Returns:
            True if adding this import would create a conflict
        """
        # Clean up the proposed import for analysis
        clean_proposed = proposed_import.replace('import ', '').replace('static ', '').replace(';', '').strip()
        
        # Determine proposed import's JUnit version
        proposed_junit_version = None
        if 'org.junit.jupiter' in clean_proposed:
            proposed_junit_version = "5"
        elif ('org.junit.Test' in clean_proposed or 
              'org.junit.Assert' in clean_proposed or 
              'org.junit.Before' in clean_proposed or 
              'org.junit.After' in clean_proposed or
              'org.junit.Assume' in clean_proposed):
            proposed_junit_version = "4"
        
        if not proposed_junit_version:
            return False  # Not a JUnit import, no conflict possible
        
        # Check existing imports for opposite version
        for import_stmt in existing_imports:
            clean_existing = import_stmt.replace('import ', '').replace('static ', '').replace(';', '').strip()
            
            if proposed_junit_version == "5":
                # Proposing JUnit 5, check for existing JUnit 4
                if (('org.junit.Test' in clean_existing or 
                     'org.junit.Assert' in clean_existing or 
                     'org.junit.Before' in clean_existing or 
                     'org.junit.After' in clean_existing or
                     'org.junit.Assume' in clean_existing) and 
                    'jupiter' not in clean_existing):
                    return True
            else:
                # Proposing JUnit 4, check for existing JUnit 5
                if 'org.junit.jupiter' in clean_existing:
                    return True
        
        return False
    
    def _analyze_hamcrest_requirements(self, code: str, existing_imports: Set[str]) -> List[ImportRequirement]:
        """Analyze Hamcrest requirements with version-specific handling."""
        requirements = []
        
        # Choose the appropriate Hamcrest matchers based on version and dependency info
        if self.hamcrest_version == "1.x" or self.dependency_info.get("format") == "hamcrest-all":
            # Use CoreMatchers for Hamcrest 1.x/hamcrest-all
            hamcrest_matchers = self.HAMCREST_CORE_MATCHERS
            logger.debug("Using Hamcrest 1.x CoreMatchers for compatibility")
        else:
            # Use modern Matchers for Hamcrest 2.x
            hamcrest_matchers = self.HAMCREST_MATCHERS
        
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
        
        return requirements
    
    def _analyze_mockito_requirements(self, code: str, existing_imports: Set[str]) -> List[ImportRequirement]:
        """Analyze Mockito requirements and ensure proper static import format."""
        requirements = []
        
        # Common Mockito static methods that should be imported statically
        mockito_static_methods = {
            r'\bmock\s*\(': 'org.mockito.Mockito.mock',
            r'\bspy\s*\(': 'org.mockito.Mockito.spy',
            r'\bwhen\s*\(': 'org.mockito.Mockito.when',
            r'\bverify\s*\(': 'org.mockito.Mockito.verify',
            r'\btimes\s*\(': 'org.mockito.Mockito.times',
            r'\bnever\s*\(': 'org.mockito.Mockito.never',
            r'\banyString\s*\(': 'org.mockito.Mockito.anyString',
            r'\banyInt\s*\(': 'org.mockito.Mockito.anyInt',
            r'\banyLong\s*\(': 'org.mockito.Mockito.anyLong',
            r'\banyObject\s*\(': 'org.mockito.Mockito.anyObject',
            r'\bany\s*\(': 'org.mockito.Mockito.any',
            r'\bdoReturn\s*\(': 'org.mockito.Mockito.doReturn',
            r'\bdoThrow\s*\(': 'org.mockito.Mockito.doThrow',
            r'\bdoNothing\s*\(': 'org.mockito.Mockito.doNothing',
            r'\bdoAnswer\s*\(': 'org.mockito.Mockito.doAnswer',
            r'\binOrder\s*\(': 'org.mockito.Mockito.inOrder',
        }
        
        for pattern, import_class in mockito_static_methods.items():
            if re.search(pattern, code):
                # Ensure proper static import format
                static_import = f"static {import_class}"
                method_name = import_class.split('.')[-1]
                
                if not self._is_import_satisfied(static_import, existing_imports):
                    requirements.append(ImportRequirement(
                        import_statement=static_import,
                        reason=f"Code uses Mockito.{method_name}",
                        priority=2
                    ))
        
        # Check for ArgumentCaptor usage
        if re.search(r'\bArgumentCaptor\b', code):
            captor_import = "org.mockito.ArgumentCaptor"
            if not self._is_import_satisfied(captor_import, existing_imports):
                requirements.append(ImportRequirement(
                    import_statement=captor_import,
                    reason="Code uses ArgumentCaptor",
                    priority=2
                ))
        
        # Check for Matchers usage (different from Hamcrest)
        mockito_matchers = {
            r'\bMatchers\.': 'org.mockito.Matchers',
            r'\beq\s*\(': 'org.mockito.Matchers.eq',
            r'\bmatches\s*\(': 'org.mockito.Matchers.matches',
        }
        
        for pattern, import_class in mockito_matchers.items():
            if re.search(pattern, code):
                if 'eq(' in pattern or 'matches(' in pattern:
                    static_import = f"static {import_class}"
                    if not self._is_import_satisfied(static_import, existing_imports):
                        requirements.append(ImportRequirement(
                            import_statement=static_import,
                            reason=f"Code uses {import_class.split('.')[-1]}",
                            priority=2
                        ))
                else:
                    if not self._is_import_satisfied(import_class, existing_imports):
                        requirements.append(ImportRequirement(
                            import_statement=import_class,
                            reason="Code uses Mockito Matchers",
                            priority=2
                        ))
        
        return requirements
    

    
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
    
    def clean_incorrect_imports(self, content: str) -> str:
        """Clean up incorrect import statements that might have been generated."""
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Skip problematic import patterns
            if stripped.startswith('import ') and not stripped.startswith('import static '):
                # Check for method-level imports that should be static
                problematic_patterns = [
                    r'import\s+org\.mockito\.Mockito\.[a-zA-Z_][a-zA-Z0-9_]*\s*;',
                    r'import\s+org\.hamcrest\..*\.[a-zA-Z_][a-zA-Z0-9_]*\s*;',
                    r'import\s+junit\.framework\.TestCase\.[a-zA-Z_][a-zA-Z0-9_]*\s*;',
                    r'import\s+org\.junit\.Assert\.[a-zA-Z_][a-zA-Z0-9_]*\s*;',
                    r'import\s+org\.mockito\.Matchers\.[a-zA-Z_][a-zA-Z0-9_]*\s*;',
                    r'import\s+org\.junit\.jupiter\.api\.Assertions\.[a-zA-Z_][a-zA-Z0-9_]*\s*;',
                ]
                
                is_problematic = False
                for pattern in problematic_patterns:
                    if re.match(pattern, stripped):
                        logger.debug(f"Removing problematic import: {stripped}")
                        is_problematic = True
                        break
                
                if is_problematic:
                    continue
                
                # Check for other invalid patterns
                if (any(invalid in stripped for invalid in ['.class;', '.getName;', '.getCanonicalName;']) and
                    not stripped.endswith('.class;') and
                    not stripped.endswith('.getName;') and
                    not stripped.endswith('.getCanonicalName;')):
                    logger.debug(f"Removing invalid import pattern: {stripped}")
                    continue
                
                # Check for imports with invalid characters
                if any(invalid in stripped for invalid in ['(', ')', '[', ']', '{', '}', '=', '"', "'"]):
                    logger.debug(f"Removing import with invalid characters: {stripped}")
                    continue
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    def _correct_junit5_assertion_arguments(self, code: str) -> str:
        """Corrects common argument order mistakes in JUnit 5 assertions."""
        if self.junit_version != "5":
            return code

        # Pattern to find assertTrue/assertFalse where a string literal is the first argument
        # e.g., assertTrue("message", condition) -> assertTrue(condition, "message")
        # This is to fix the common mistake of using JUnit 4 argument order in JUnit 5
        pattern = re.compile(r'\b(assertTrue|assertFalse)\s*\(\s*("((?:\\.|[^"\\])*)")\s*,\s*([^)]+)\s*\)')
        
        def replacer(match):
            method, message, _, condition = match.groups()
            logger.debug(f"Correcting JUnit 5 assertion argument order for: {method}")
            return f"{method}({condition.strip()}, {message})"

        corrected_code = pattern.sub(replacer, code)
        
        return corrected_code
    
    def add_missing_imports(self, content: str, additional_imports: List[str]) -> Tuple[str, bool]:
        """
        Enhanced import adding that corrects API usage and automatically adds missing imports.
        
        Args:
            content: Original Java file content
            additional_imports: List of manually specified imports
            
        Returns:
            Tuple of (modified_content, success)
        """
        # First, correct common API usage mistakes before analyzing imports
        content = self._correct_junit5_assertion_arguments(content)

        # Then, clean up any incorrect imports
        content = self.clean_incorrect_imports(content)
        
        # Get existing imports first
        existing_imports = self.extract_existing_imports(content)
        
        # Analyze code to find required imports, considering existing ones
        code_requirements = self.analyze_code_requirements(content, existing_imports)
        
        # Combine manual imports with auto-detected ones
        all_imports = set()
        
        # Process manual imports first (normalize format)
        if additional_imports:
            for imp in additional_imports:
                cleaned = self._normalize_import_format(imp, content)
                if cleaned:
                    all_imports.add(cleaned)
        
        # Add auto-detected imports
        for req in code_requirements:
            normalized = self._normalize_import_format(req.import_statement, content)
            if normalized:
                all_imports.add(normalized)
                logger.debug(f"Auto-detected import need: {normalized} ({req.reason})")
        
        if not all_imports:
            logger.debug("No new imports needed")
            return content, True
        
        # Filter out imports that already exist and remove redundant imports
        new_imports = []
        wildcard_imports = set()  # Track wildcard imports to avoid redundant specific imports
        
        for imp in all_imports:
            # Check if this import is already satisfied
            if not self._is_import_satisfied(imp, existing_imports):
                # Format as proper import statement
                formatted_import = self._format_import_statement(imp)
                
                # Check for wildcard imports and avoid redundant specific imports
                if formatted_import.endswith('.*;'):
                    # This is a wildcard import
                    wildcard_base = formatted_import[:-3]  # Remove '.*;'
                    wildcard_imports.add(wildcard_base)
                    new_imports.append(formatted_import)
                else:
                    # Check if this specific import is covered by a wildcard
                    import_base = formatted_import.replace('import ', '').replace(';', '')
                    if 'static ' in import_base:
                        # For static imports, check if there's a wildcard for the same class
                        static_part = import_base.replace('static ', '')
                        if '.' in static_part:
                            class_path = '.'.join(static_part.split('.')[:-1])
                            wildcard_key = f"import static {class_path}"
                            if wildcard_key not in wildcard_imports:
                                new_imports.append(formatted_import)
                            else:
                                logger.debug(f"Skipping redundant static import (covered by wildcard): {imp}")
                        else:
                            new_imports.append(formatted_import)
                    else:
                        # For regular imports, check if there's a wildcard for the same package
                        if '.' in import_base:
                            package_path = '.'.join(import_base.split('.')[:-1])
                            wildcard_key = f"import {package_path}"
                            if wildcard_key not in wildcard_imports:
                                new_imports.append(formatted_import)
                            else:
                                logger.debug(f"Skipping redundant import (covered by wildcard): {imp}")
                        else:
                            new_imports.append(formatted_import)
            else:
                logger.debug(f"Import already satisfied: {imp}")
        
        if not new_imports:
            logger.debug("All required imports already exist or are satisfied")
            return content, True
        
        return self._insert_imports(content, new_imports)
    
    def _normalize_import_format(self, import_statement: str, test_file_content: str = None) -> str:
        """
        Normalize import format to ensure consistency and fix common errors.
        
        Args:
            import_statement: The import statement to normalize
            test_file_content: Optional test file content for context validation
        """
        if not import_statement:
            return ""
        
        # Remove 'import ' prefix and ';' suffix if present
        cleaned = import_statement.strip()
        if cleaned.startswith('import '):
            cleaned = cleaned[7:]  # Remove 'import '
        if cleaned.endswith(';'):
            cleaned = cleaned[:-1]  # Remove ';'
        
        cleaned = cleaned.strip()
        
        # Filter out comments and invalid import statements
        if (not cleaned or 
            cleaned.startswith('#') or 
            cleaned.startswith('//') or 
            cleaned.startswith('/*') or
            cleaned.lower() in ['none', 'n/a', 'empty', 'no new imports required', 'original imports remain sufficient'] or
            'no new imports required' in cleaned.lower() or
            'original imports remain sufficient' in cleaned.lower() or
            any(invalid in cleaned for invalid in ['(', ')', '[', ']', '{', '}', '=', '"', "'"])):
            logger.debug(f"Filtering out invalid import statement: {cleaned}")
            return ""
        
        # Validate that it looks like a valid import (contains at least one dot for package structure)
        if not ('.' in cleaned and not cleaned.startswith('.') and not cleaned.endswith('.')):
            logger.debug(f"Filtering out malformed import: {cleaned}")
            return ""
        
        # Additional validation: must contain at least one uppercase letter (class name)
        # Valid Java imports should have at least one class name (starts with uppercase)
        if not any(c.isupper() for c in cleaned):
            logger.debug(f"Filtering out import without class name: {cleaned}")
            return ""
        
        # CRITICAL: Filter out invalid static imports for annotations and classes that should not be static
        if cleaned.startswith('static '):
            static_part = cleaned[7:]  # Remove 'static ' prefix
            
            # Check for imports that should NEVER be static imports
            invalid_static_patterns = [
                r'org\.junit\.jupiter\.api\.Test$',      # @Test annotation 
                r'org\.junit\.Test$',                    # @Test annotation (JUnit 4)
                r'org\.junit\..*\.Before$',              # @Before annotation
                r'org\.junit\..*\.After$',               # @After annotation
                r'org\.junit\..*\.BeforeEach$',          # @BeforeEach annotation
                r'org\.junit\..*\.AfterEach$',           # @AfterEach annotation
                r'org\.junit\..*\.BeforeAll$',           # @BeforeAll annotation
                r'org\.junit\..*\.AfterAll$',            # @AfterAll annotation
                r'org\.junit\..*\.ParameterizedTest$',   # @ParameterizedTest annotation
                r'org\.junit\..*\.TestInstance$',        # @TestInstance annotation
                r'org\.junit\..*\.TestMethodOrder$',     # @TestMethodOrder annotation
                r'org\.junit\..*\.DisplayName$',         # @DisplayName annotation
                r'org\.junit\..*\.Disabled$',            # @Disabled annotation
                r'org\.junit\..*\.Tag$',                 # @Tag annotation
                r'.*\.Test$',                            # Any Test annotation
                r'.*\.Before$',                          # Any Before annotation
                r'.*\.After$',                           # Any After annotation
            ]
            
            for pattern in invalid_static_patterns:
                if re.match(pattern, static_part):
                    logger.debug(f"Filtering out invalid static import for annotation/class: {cleaned}")
                    return ""
        
        # Validate production imports if test file content is available
        if test_file_content:
            production_analysis = self.analyze_production_imports([cleaned], test_file_content)
            if production_analysis['package_mismatches']:
                for mismatch in production_analysis['package_mismatches']:
                    logger.warning(f"Potential package mismatch in import: {mismatch['import']}")
                    logger.warning(f"Expected package prefix: {mismatch['expected_package']}")
                    # For now, just warn - we could potentially auto-correct in the future
        
        # Automatically detect and fix method-level imports that should be static
        # e.g., "org.junit.Assert.assertEquals" -> "static org.junit.Assert.assertEquals"
        # This pattern checks if the last segment starts with a lowercase letter (a method)
        # and the second-to-last segment starts with an uppercase letter (a class).
        match = re.match(r'^(.*\.[A-Z][a-zA-Z0-9_]*)\.([a-z][a-zA-Z0-9_]*)$', cleaned)
        if match and not cleaned.startswith('static '):
            class_path, method_name = match.groups()
            
            # Whitelist of classes we know provide static methods for testing
            known_static_providers = [
                'org.junit.Assert', 'org.junit.jupiter.api.Assertions',
                'org.mockito.Mockito', 'org.mockito.Matchers',
                'org.hamcrest.MatcherAssert', 'org.hamcrest.Matchers', 'org.hamcrest.CoreMatchers',
                'org.junit.Assume', 'org.junit.jupiter.api.Assumptions'
            ]
            
            if any(class_path.startswith(provider) for provider in known_static_providers):
                logger.debug(f"Correcting malformed static import: {cleaned}")
                return f"static {cleaned}"
        
        return cleaned
    
    def _is_import_satisfied(self, required_import: str, existing_imports: Set[str]) -> bool:
        """
        Check if a required import is already satisfied by existing imports.
        This handles direct matches, wildcard matches, class vs static imports, and malformed static imports.
        
        Args:
            required_import: The import we need (e.g., "static org.junit.jupiter.api.Assertions.assertEquals")
            existing_imports: Set of existing import statements from the file
            
        Returns:
            True if the import is already satisfied
        """
        # Normalize the required import to a consistent, full format.
        # This will fix missing "static" and add "import ...;" wrappers.
        normalized_required = self._format_import_statement(required_import)

        # 1. Direct match check
        for existing in existing_imports:
            # Also normalize the existing import to handle any inconsistencies
            normalized_existing = self._format_import_statement(existing)
            if self._normalize_import(normalized_existing) == self._normalize_import(normalized_required):
                return True
        
        # 2. For static imports, check if a class-level import already exists
        # This handles cases where we try to add "static org.junit.jupiter.api.Test" 
        # when "org.junit.jupiter.api.Test" already exists
        if 'static' in normalized_required:
            static_import_part = normalized_required.replace('import static ', '').replace(';', '').strip()
            
            # Extract the class part (before the last dot, if it exists)
            if '.' in static_import_part:
                class_part = '.'.join(static_import_part.split('.')[:-1])
                class_import = f"import {class_part};"
                
                # Check if this class is already imported (non-static)
                for existing in existing_imports:
                    normalized_existing = self._format_import_statement(existing)
                    if self._normalize_import(normalized_existing) == self._normalize_import(class_import):
                        logger.debug(f"Static import {required_import} satisfied by existing class import: {existing}")
                        return True
            
            # Check for class-level wildcards (e.g., import static org.junit.Assert.*;)
            import_parts = static_import_part.split('.')
            if len(import_parts) > 1:
                class_path = '.'.join(import_parts[:-1])
                wildcard_import = f"import static {class_path}.*;"
                
                for existing in existing_imports:
                    normalized_existing = self._format_import_statement(existing)
                    if self._normalize_import(normalized_existing) == self._normalize_import(wildcard_import):
                        return True

        # 3. For regular class imports, check for package-level wildcards (e.g., import java.util.*;)
        else:
            # Extract package name: "import java.util.List;" -> "java.util"
            import_content = normalized_required.replace('import ', '').replace(';', '').strip()
            if '.' in import_content:
                package_name = '.'.join(import_content.split('.')[:-1])
                wildcard_import = f"import {package_name}.*;"
                
                for existing in existing_imports:
                    normalized_existing = self._format_import_statement(existing)
                    if self._normalize_import(normalized_existing) == self._normalize_import(wildcard_import):
                        return True
        
        return False

    def _format_import_statement(self, import_spec: str) -> str:
        """Format an import specification into a proper import statement."""
        if not import_spec:
            return ""
        
        # Add 'import ' prefix if not present
        if not import_spec.startswith('import '):
            # Use our enhanced normalizer to ensure 'static' is present if needed
            normalized_spec = self._normalize_import_format(import_spec)
            formatted = f"import {normalized_spec};"
        else:
            # Already has 'import ' prefix, just ensure it ends with ';'
            formatted = import_spec.rstrip()
            if not formatted.endswith(';'):
                formatted += ';'

        return formatted
    
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

    def analyze_third_party_dependencies(self, imports: List[str]) -> List[Dict[str, Any]]:
        """
        Analyze import list to determine required third-party dependencies.
        
        Args:
            imports: List of import statements to analyze
            
        Returns:
            List of dependency requirements with type and specific imports
        """
        dependencies = []
        
        # Group imports by dependency type
        hamcrest_imports = []
        mockito_imports = []
        
        for imp in imports:
            imp_lower = imp.lower()
            if any(hamcrest_pkg in imp_lower for hamcrest_pkg in ['hamcrest']):
                hamcrest_imports.append(imp)
            elif any(mockito_pkg in imp_lower for mockito_pkg in ['mockito']):
                mockito_imports.append(imp)
        
        # Add dependency requirements
        if hamcrest_imports:
            dependencies.append({
                'type': 'hamcrest',
                'imports': hamcrest_imports,
                'reason': f'Code uses {len(hamcrest_imports)} Hamcrest imports'
            })
        
        if mockito_imports:
            dependencies.append({
                'type': 'mockito',
                'imports': mockito_imports,
                'reason': f'Code uses {len(mockito_imports)} Mockito imports'
            })
        
        return dependencies

    def analyze_production_imports(self, imports: List[str], test_file_content: str) -> Dict[str, Any]:
        """
        Analyze production function imports for potential issues.
        
        Args:
            imports: List of import statements to analyze
            test_file_content: Content of the test file to extract context
            
        Returns:
            Dictionary containing analysis results and recommendations
        """
        analysis = {
            'suspicious_imports': [],
            'package_mismatches': [],
            'recommendations': [],
            'test_package': None
        }
        
        # Extract test package from file content
        package_match = re.search(r'package\s+([\w\.]+);', test_file_content)
        if package_match:
            analysis['test_package'] = package_match.group(1)
        
        # Common testing frameworks and utilities (should not be flagged)
        testing_patterns = [
            'junit', 'testng', 'hamcrest', 'mockito', 'powermock', 'easymock',
            'assertj', 'truth', 'wiremock', 'testcontainers'
        ]
        
        for imp in imports:
            # Skip if it's a testing framework
            if any(pattern in imp.lower() for pattern in testing_patterns):
                continue
            
            # Skip static imports (usually for utility methods)
            if imp.startswith('static '):
                continue
            
            # Check for potential production class imports
            import_lower = imp.lower()
            
            # Look for patterns that suggest production code imports
            if self._is_likely_production_import(imp):
                analysis['suspicious_imports'].append({
                    'import': imp,
                    'reason': 'Potential production class import - verify necessity'
                })
                
                # Check for package name mismatches
                if analysis['test_package']:
                    expected_production_package = self._infer_production_package(analysis['test_package'])
                    if expected_production_package:
                        # Special case for beanutils/beanutils2 mismatch
                        if 'beanutils2' in expected_production_package and 'beanutils' in imp and 'beanutils2' not in imp:
                            analysis['package_mismatches'].append({
                                'import': imp,
                                'expected_package': expected_production_package,
                                'reason': f'Import uses old package "beanutils" instead of "beanutils2"'
                            })
                        elif not imp.startswith(expected_production_package):
                            # Check if it's a reasonable mismatch (not just different project entirely)
                            imp_base = '.'.join(imp.split('.')[:3])  # Get base package like org.apache.commons
                            expected_base = '.'.join(expected_production_package.split('.')[:3])
                            if imp_base == expected_base:  # Same base project, different subpackage
                                analysis['package_mismatches'].append({
                                    'import': imp,
                                    'expected_package': expected_production_package,
                                    'reason': f'Import may have wrong package name for project structure'
                                })
        
        # Generate recommendations
        if analysis['package_mismatches']:
            analysis['recommendations'].append(
                "Check package names for production imports - they may not match the project structure"
            )
        
        if analysis['suspicious_imports']:
            analysis['recommendations'].append(
                "Consider if production class imports are necessary for the refactoring goal"
            )
        
        return analysis
    
    def _is_likely_production_import(self, import_statement: str) -> bool:
        """Check if an import is likely a production class import."""
        # Skip Java standard library
        if import_statement.startswith('java.') or import_statement.startswith('javax.'):
            return False
        
        # Skip testing frameworks - more comprehensive list
        testing_frameworks = [
            'junit', 'testng', 'hamcrest', 'mockito', 'powermock', 'easymock',
            'assertj', 'truth', 'wiremock', 'testcontainers'
        ]
        
        import_lower = import_statement.lower()
        if any(framework in import_lower for framework in testing_frameworks):
            return False
        
        # Skip common testing utilities - be more specific
        testing_keywords = [
            'test', 'mock', 'stub', 'fake', 'spy', 'fixture', 'builder', 
            'helper', 'support', 'runner', 'rule', 'testutil'
        ]
        
        # Only skip if the keyword is a significant part of the import
        # For example, skip "TestUtils" but not "PropertyUtils"
        for keyword in testing_keywords:
            if keyword in import_lower:
                # Check if it's part of a class name or package name
                parts = import_statement.split('.')
                for part in parts:
                    if keyword in part.lower() and (
                        part.lower().startswith(keyword) or 
                        part.lower().endswith(keyword) or
                        keyword == 'test'  # 'test' is always significant
                    ):
                        return False
        
        # Skip annotations and wildcard imports
        if import_statement.endswith('.*') or '.' not in import_statement:
            return False
        
        # If it contains a specific project pattern and looks like a class import, it's likely production
        # Check if it looks like a class import (ends with a capitalized word)
        parts = import_statement.split('.')
        if parts and parts[-1] and parts[-1][0].isupper():
            return True
        
        return False
    
    def _infer_production_package(self, test_package: str) -> Optional[str]:
        """
        Infer the corresponding production package from test package.
        
        Args:
            test_package: The package name of the test class
            
        Returns:
            Expected production package name, or None if cannot be inferred
        """
        # For commons-beanutils specifically: beanutils2 is the current version
        # Any import to beanutils (without 2) might be wrong
        if 'beanutils2' in test_package:
            return test_package  # Production should also use beanutils2
        
        # Common test package patterns and their production equivalents
        test_patterns = [
            ('test.java.', ''),  # src/test/java/com.example -> src/main/java/com.example
            ('.test.', '.'),     # com.example.test.unit -> com.example.unit
            ('.tests.', '.'),    # com.example.tests.unit -> com.example.unit
        ]
        
        for test_pattern, replacement in test_patterns:
            if test_pattern in test_package:
                return test_package.replace(test_pattern, replacement)
        
        # If no pattern matches, try removing common test suffixes
        if test_package.endswith('.test') or test_package.endswith('.tests'):
            return '.'.join(test_package.split('.')[:-1])
        
        # Default: test package and production package are the same
        # This is common in many projects where test classes are in the same package
        return test_package

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