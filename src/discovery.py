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
    
    def find_test_file(self, test_class_name: str) -> Optional[Path]:
        """Find the Java test file for a given test class, supporting multi-module projects."""
        # Convert fully qualified class name to file path
        class_path_parts = test_class_name.split('.')
        class_file_name = class_path_parts[-1] + '.java'
        full_class_path = '/'.join(class_path_parts) + '.java'
        
        # Strategy 1: Direct search using glob pattern for the exact file name
        # This is faster and works for most cases
        for pattern in [f"**/*/{class_file_name}", f"**/src/test/java/**/{class_file_name}"]:
            matching_files = list(self.java_project_path.glob(pattern))
            
            # Filter to find exact matches based on package structure
            for file_path in matching_files:
                # Check if the file path matches the expected package structure
                file_path_str = str(file_path)
                if full_class_path in file_path_str:
                    logger.debug(f"Found test file using pattern '{pattern}': {file_path}")
                    return file_path
            
            # If no exact match, try the first match (fallback)
            if matching_files:
                logger.debug(f"Using first match from pattern '{pattern}': {matching_files[0]}")
                return matching_files[0]
        
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
    
    def validate_test_cases(self, test_cases: List[TestCase]) -> List[TestCase]:
        """Validate test cases by finding files and checking executability using multithreading."""
        from .validator import CodeValidator
        
        validator = CodeValidator(self.java_project_path)
        
        logger.info("Performing initial project build...")
        compile_success, compile_output = validator.compile_java_project()
        if not compile_success:
            logger.warning("Initial project build failed. Continuing with file discovery only.")
            logger.warning(f"Build output:\n{compile_output}")
            
            # In debug mode, provide more detailed build failure information
            debug_logger = logging.getLogger('aif')
            if debug_logger.isEnabledFor(logging.DEBUG):
                logger.debug("=" * 60)
                logger.debug("DETAILED BUILD FAILURE ANALYSIS")
                logger.debug("=" * 60)
                logger.debug(f"Project path: {self.java_project_path}")
                logger.debug(f"Build system detected: {validator._detect_build_system()}")
                logger.debug(f"Full build output:\n{compile_output}")
                logger.debug("=" * 60)
            
            # Continue with file discovery even if build fails
            logger.info("⚠ Build failed, but will still attempt to find test files for inspection")
            build_failed = True
        else:
            logger.info("✓ Initial project build successful.")
            build_failed = False

        # Define a worker function for each thread
        def _validate_worker(test_case: TestCase) -> TestCase:
            test_file = self.find_test_file(test_case.test_class_name)
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
                    
                    # Categorize test results
                    if test_success:
                        test_case.pass_status = "pass"
                    elif "COMPILATION ERROR" in test_output or "cannot find symbol" in test_output:
                        test_case.pass_status = "compilation_error"
                    elif "BUILD FAILURE" in test_output:
                        test_case.pass_status = "build_failure" 
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
            logger.info(f"Note: All tests marked as non-runnable due to build failure")
        else:
            logger.info(f"Runnable test cases: {runnable_cases}/{len(validated_cases)}")
        
        return sorted(validated_cases, key=lambda tc: test_cases.index(tc))
    
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