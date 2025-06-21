"""Test discovery and validation logic."""

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

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
        """Find the Java test file for a given test class."""
        # Convert fully qualified class name to file path
        class_path = test_class_name.replace('.', '/') + '.java'
        
        # Search in common test directories
        test_dirs = ['src/test/java', 'test', 'tests']
        
        for test_dir in test_dirs:
            test_file = self.java_project_path / test_dir / class_path
            if test_file.exists():
                return test_file
        
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
        
        # Define a worker function for each thread
        def _validate_worker(test_case: TestCase) -> TestCase:
            test_file = self.find_test_file(test_case.test_class_name)
            if test_file:
                test_case.test_path = str(test_file)
                test_case.test_case_loc = self.count_lines_of_code(test_file, test_case.test_method_name)
                
                # Assume runnable, will be confirmed by test execution
                test_case.runable = "yes"
                
                # Execute test
                test_success, test_output = validator.run_specific_test(
                    test_case.test_class_name, 
                    test_case.test_method_name
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
                test_case.pass_status = "not_found"
            return test_case

        validated_cases = []
        # Use ThreadPoolExecutor to run validations in parallel
        # Limiting workers to 10 to avoid overwhelming the system with mvn processes
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Create a future for each test case
            future_to_case = {executor.submit(_validate_worker, tc): tc for tc in test_cases}
            
            # Process as they complete, with a progress bar
            for future in tqdm(as_completed(future_to_case), total=len(test_cases), desc="Validating test cases"):
                try:
                    validated_case = future.result()
                    validated_cases.append(validated_case)
                except Exception as exc:
                    case = future_to_case[future]
                    print(f"\nError validating {case.test_method_name}: {exc}")
                    # Mark as failed if an exception occurs
                    case.pass_status = "validation_error"
                    validated_cases.append(case)
        
        return sorted(validated_cases, key=lambda tc: test_cases.index(tc))
    
    def save_refactor_cases_csv(self, test_cases: List[TestCase], output_path: Path) -> None:
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