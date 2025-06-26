"""Test discovery and validation logic."""

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import logging

logger = logging.getLogger('aif')

class TestCase:
    """Represents a test case with metadata."""
    
    def __init__(self, project_name: str, test_class_name: str, test_method_name: str, issue_type: str):
        self.project_name = project_name
        self.test_class_name = test_class_name
        self.test_method_name = test_method_name
        self.issue_type = issue_type
        self.test_path: Optional[str] = None
        self.test_case_loc: Optional[int] = None
        self.runable: str = "no"
        self.pass_status: str = "no"

class TestDiscovery:
    """Handles test case discovery and validation."""
    
    def __init__(self, java_project_path: Path, data_folder_path: Path):
        self.java_project_path = java_project_path
        self.data_folder_path = data_folder_path
    
    def load_aaa_results(self) -> List[TestCase]:
        """Load test cases from AAA results CSV file."""
        # Find CSV file matching pattern: <project_name> AAAResults.csv
        csv_files = list(self.data_folder_path.glob("* AAAResults.csv"))
        if not csv_files:
            raise FileNotFoundError("No AAA results CSV file found")
        
        csv_file = csv_files[0]
        test_cases = []
        
        with open(csv_file, 'r', encoding='utf-8-sig') as f:  # Handle BOM
            reader = csv.DictReader(f)
            for row in reader:
                test_case = TestCase(
                    project_name=row.get('project', ''),  # Updated column name
                    test_class_name=row.get('class_name', ''),  # Updated column name
                    test_method_name=row.get('test_case_name', ''),  # Updated column name
                    issue_type=row.get('issue_type', '')
                )
                test_cases.append(test_case)
        
        return test_cases
    
    def find_test_file(self, test_class_name: str, method_name: Optional[str] = None) -> Optional[Path]:
        """Find the Java test file for a given test class, supporting multi-module projects.
        
        Args:
            test_class_name: Fully qualified class name (e.g., org.apache.tika.parser.html.HtmlParserTest)
            method_name: Optional test method name for verification
            
        Returns:
            Path to the correct test file, or None if not found
        """
        # Convert fully qualified class name to file path
        class_path_parts = test_class_name.split('.')
        class_file_name = class_path_parts[-1] + '.java'
        full_class_path = '/'.join(class_path_parts) + '.java'
        
        logger.debug(f"Searching for test file: {test_class_name}")
        if method_name:
            logger.debug(f"  Target method: {method_name}")
        
        # Strategy 1: Direct search using glob pattern for the exact file name
        # This is faster and works for most cases
        for pattern in [f"**/*/{class_file_name}", f"**/src/test/java/**/{class_file_name}"]:
            matching_files = list(self.java_project_path.glob(pattern))
            logger.debug(f"  Pattern '{pattern}' found {len(matching_files)} files")
            
            if not matching_files:
                continue
                
            # Strategy 1a: Find exact matches based on package structure
            exact_matches = []
            for file_path in matching_files:
                file_path_str = str(file_path)
                if full_class_path in file_path_str:
                    exact_matches.append(file_path)
                    logger.debug(f"    Exact package match: {file_path}")
            
            # Strategy 1b: If we have method name, verify which file contains the method
            if method_name and len(exact_matches) > 1:
                logger.debug(f"    Multiple exact matches found, verifying method '{method_name}'...")
                for file_path in exact_matches:
                    if self._file_contains_method(file_path, method_name):
                        logger.debug(f"    ✓ Method verified in: {file_path}")
                        return file_path
                    else:
                        logger.debug(f"    ✗ Method not found in: {file_path}")
            elif exact_matches:
                # Single exact match or no method to verify
                chosen_file = exact_matches[0]
                logger.debug(f"Found test file using exact package match: {chosen_file}")
                return chosen_file
            
            # Strategy 1c: If no exact package match, verify method in all candidates
            if method_name:
                logger.debug(f"    No exact package matches, checking method in all {len(matching_files)} files...")
                for file_path in matching_files:
                    if self._file_contains_method(file_path, method_name):
                        logger.debug(f"    ✓ Method found in: {file_path}")
                        return file_path
                    else:
                        logger.debug(f"    ✗ Method not found in: {file_path}")
            
            # Strategy 1d: Last resort - use first match (old behavior)
            if matching_files:
                chosen_file = matching_files[0]
                logger.debug(f"Using first match from pattern '{pattern}': {chosen_file}")
                return chosen_file
        
        # Strategy 2: Traditional directory-based search (legacy support)
        # Search in common test directories at project root
        test_dirs = ['src/test/java', 'test', 'tests']
        
        for test_dir in test_dirs:
            test_file = self.java_project_path / test_dir / full_class_path
            if test_file.exists():
                logger.debug(f"Found test file in root directory: {test_file}")
                return test_file
        
        # Strategy 3: Recursive search in all subdirectories (for complex project structures)
        logger.debug(f"Performing recursive search for class: {test_class_name}")
        
        # Search for any file with the class name in test directories
        for test_dir_pattern in ["**/src/test/java", "**/test", "**/tests"]:
            test_dirs = list(self.java_project_path.glob(test_dir_pattern))
            for test_dir in test_dirs:
                if test_dir.is_dir():
                    potential_file = test_dir / full_class_path
                    if potential_file.exists():
                        logger.debug(f"Found test file in subdirectory: {potential_file}")
                        return potential_file
        
        logger.debug(f"Test file not found for class: {test_class_name}")
        return None
    
    def _file_contains_method(self, file_path: Path, method_name: str) -> bool:
        """Check if a Java file contains a specific test method.
        
        Args:
            file_path: Path to the Java file
            method_name: Method name to search for
            
        Returns:
            True if the method is found in the file
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for method signatures with various patterns:
            # 1. @Test annotation followed by method
            # 2. Direct method declaration
            import re
            
            # Pattern 1: @Test annotation somewhere before method declaration
            test_annotation_pattern = r'@Test\s*(?:\([^)]*\))?\s*(?:public\s+)?(?:static\s+)?void\s+' + re.escape(method_name) + r'\s*\('
            if re.search(test_annotation_pattern, content, re.MULTILINE | re.DOTALL):
                return True
            
            # Pattern 2: Simple method declaration
            method_pattern = r'(?:public\s+)?(?:static\s+)?void\s+' + re.escape(method_name) + r'\s*\('
            if re.search(method_pattern, content, re.MULTILINE):
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error reading file {file_path}: {e}")
            return False
    
    def count_lines_of_code(self, file_path: Path, method_name: str) -> int:
        """Count lines of code for a specific test method."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple method to count LOC - could be improved with proper Java parsing
            lines = content.split('\n')
            in_method = False
            brace_count = 0
            loc = 0
            
            for line in lines:
                stripped = line.strip()
                if not in_method and f'void {method_name}(' in line:
                    in_method = True
                
                if in_method:
                    if stripped and not stripped.startswith('//'):
                        loc += 1
                    
                    # Count braces to determine method end
                    brace_count += line.count('{') - line.count('}')
                    if brace_count == 0 and in_method and '{' in line:
                        break
            
            return max(1, loc)  # Ensure at least 1 LOC
        except Exception:
            return 1
    
    def validate_test_cases(self, test_cases: List[TestCase], skip_initial_build: bool = False,
                          fallback_manual: bool = True, build_timeout: int = 600) -> List[TestCase]:
        """Validate test cases by finding files and checking executability using smart build management."""
        from .validator import CodeValidator
        from .build_system import SmartBuildManager
        
        validator = CodeValidator(self.java_project_path)
        build_manager = SmartBuildManager(validator.build_system)
        
        logger.info("Ensuring project is properly built...")
        
        # Use smart build management
        build_success, build_message = build_manager.ensure_project_built(
            skip_build=skip_initial_build,
            fallback_manual=fallback_manual,
            timeout=build_timeout
        )
        
        if not build_success:
            logger.warning(f"⚠ Build verification failed: {build_message}")
            logger.warning("⚠ Continuing with file discovery only (tests marked as non-runnable)")
            build_failed = True
        else:
            logger.info(f"✓ Build verification successful: {build_message}")
            build_failed = False

        # Define a worker function for each thread
        def _validate_worker(test_case: TestCase) -> TestCase:
            test_file = self.find_test_file(test_case.test_class_name, test_case.test_method_name)
            if test_file:
                test_case.test_path = str(test_file)
                test_case.test_case_loc = self.count_lines_of_code(test_file, test_case.test_method_name)
                
                if build_failed:
                    # If build failed, mark as non-runnable but note that file exists
                    test_case.runable = "no"
                    test_case.pass_status = "build_failure"
                else:
                    # Assume runnable, will be confirmed by test execution
                    test_case.runable = "yes"
                    
                    # Execute test only if build was successful
                    test_success, test_output = validator.run_specific_test(
                        test_case.test_class_name, 
                        test_case.test_method_name,
                        test_file  # Pass the test file path for module detection
                    )
                    
                    # Categorize test results with enhanced error detection
                    if test_success:
                        test_case.pass_status = "pass"
                    elif "COMPILATION ERROR" in test_output or "cannot find symbol" in test_output:
                        test_case.pass_status = "compilation_error"
                    elif "BUILD FAILURE" in test_output:
                        test_case.pass_status = "build_failure"
                    elif self._is_test_setup_error(test_output):
                        test_case.pass_status = "test_setup_error"
                    else:
                        test_case.pass_status = "fail"
            else:
                test_case.test_path = "not found"
                test_case.test_case_loc = 0
                test_case.runable = "no"
                if build_failed:
                    test_case.pass_status = "file_not_found_build_failure"
                else:
                    test_case.pass_status = "not_found"
            return test_case

        validated_cases = []
        # Use ThreadPoolExecutor to run validations in parallel
        # Using only 1 worker to avoid Maven concurrency issues
        with ThreadPoolExecutor(max_workers=1) as executor:
            # Create a future for each test case
            future_to_case = {executor.submit(_validate_worker, tc): tc for tc in test_cases}
            
            # Process as they complete, with a progress bar
            progress_bar = tqdm(as_completed(future_to_case), total=len(test_cases), 
                                desc="Validating test cases",
                                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]',
                                ascii=True) # Use ASCII characters for better compatibility
            
            for future in progress_bar:
                try:
                    validated_case = future.result()
                    validated_cases.append(validated_case)
                except Exception as exc:
                    case = future_to_case[future]
                    logger.error(f"\nError validating {case.test_method_name}: {exc}")
                    # Mark as failed if an exception occurs
                    case.pass_status = "validation_error"
                    validated_cases.append(case)
        
        # Report findings
        found_files = sum(1 for tc in validated_cases if tc.test_path != "not found")
        runnable_cases = sum(1 for tc in validated_cases if tc.runable == "yes")
        
        if build_failed:
            logger.info(f"Found test files: {found_files}/{len(validated_cases)}")
            logger.info(f"Note: All tests marked as non-runnable due to build issues")
        else:
            logger.info(f"Runnable test cases: {runnable_cases}/{len(validated_cases)}")
        
        return sorted(validated_cases, key=lambda tc: test_cases.index(tc))
    
    def _is_test_setup_error(self, test_output: str) -> bool:
        """
        Check if the test failure is due to test setup/configuration issues.
        
        Args:
            test_output: The test execution output
            
        Returns:
            True if the error appears to be test setup related
        """
        setup_error_indicators = [
            "NullPointerException",
            "getProviderConfig()",
            "getReadFolder()",
            "getFileSystem()",
            "AbstractProviderTestCase",
            "Test setup",
            "test configuration",
            "provider config",
            "Cannot invoke",
            "because the return value",
            "is null"
        ]
        
        output_lower = test_output.lower()
        return any(indicator.lower() in output_lower for indicator in setup_error_indicators)
    
    def save_refactor_cases_csv(self, test_cases: List[TestCase], output_path: Path) -> Path:
        """Save validated test cases to refactor cases CSV."""
        output_file = output_path / f"{test_cases[0].project_name}_AAA_Refactor_Cases.csv"
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'project_name', 'test_class_name', 'test_method_name', 'issue_type',
                'test_path', 'test_case_LOC', 'runable', 'pass'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for test_case in test_cases:
                writer.writerow({
                    'project_name': test_case.project_name,
                    'test_class_name': test_case.test_class_name,
                    'test_method_name': test_case.test_method_name,
                    'issue_type': test_case.issue_type,
                    'test_path': test_case.test_path,
                    'test_case_LOC': test_case.test_case_loc,
                    'runable': test_case.runable,
                    'pass': test_case.pass_status
                })
        
        return output_file