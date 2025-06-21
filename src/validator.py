"""Code validation and integration utilities."""

import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple

class CodeValidator:
    """Validates and integrates refactored code."""
    
    def __init__(self, java_project_path: Path):
        self.java_project_path = java_project_path
    
    def integrate_refactored_method(self, test_file_path: Path, original_method_name: str, refactored_code: str) -> bool:
        """Integrate refactored method into the original test class."""
        try:
            # Read original file
            with open(test_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Create refactored method name
            refactored_method_name = f"{original_method_name}_refactored"
            
            # Prepare refactored code by only renaming the method
            refactored_code_prepared = self._prepare_refactored_code(refactored_code, original_method_name, refactored_method_name)
            
            # Find the best insertion point in the class
            insertion_point = self._find_insertion_point(content)
            
            if insertion_point == -1:
                print(f"Could not find insertion point in {test_file_path}")
                return False
            
            # Insert the refactored method
            lines = content.split('\n')
            
            # Add proper indentation and comments
            refactored_lines = ['']
            
            # Add refactored code with proper indentation
            for line in refactored_code_prepared.split('\n'):
                if line.strip():
                    refactored_lines.append('    ' + line)
                else:
                    refactored_lines.append('')
            
            refactored_lines.append('')
            
            # Insert at the calculated position
            # Find the line to insert before to get its indentation
            base_indentation = re.match(r'^\s*', lines[insertion_point-1]).group(0)
            for i, line in enumerate(reversed(refactored_lines)):
                lines.insert(insertion_point, base_indentation + line)
            
            # Write back to file
            with open(test_file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            return True
            
        except Exception as e:
            print(f"Error integrating refactored method: {e}")
            return False
    
    def _prepare_refactored_code(self, refactored_code: str, original_method_name: str, refactored_method_name: str) -> str:
        """Prepare refactored code for insertion by only renaming the method."""
        # Replace method name
        patterns_to_try = [
            rf'(\bpublic\s+void\s+){re.escape(original_method_name)}(\s*\()',
            rf'(\bvoid\s+){re.escape(original_method_name)}(\s*\()',
        ]
        
        for pattern in patterns_to_try:
            if re.search(pattern, refactored_code):
                refactored_code = re.sub(pattern, rf'\1{refactored_method_name}\2', refactored_code)
                break
        
        return refactored_code.strip()
    
    def _find_insertion_point(self, content: str) -> int:
        """Find the best insertion point for a new method in a Java class."""
        lines = content.split('\n')
        
        # Strategy 1: Find the last method and insert after it
        last_method_end = -1
        brace_count = 0
        in_method = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Detect method start
            if re.search(r'(public|private|protected)?\s*(static\s+)?void\s+\w+\s*\([^)]*\)\s*{?', stripped):
                in_method = True
                brace_count = 0
                if '{' in stripped:
                    brace_count += stripped.count('{') - stripped.count('}')
            elif in_method:
                brace_count += stripped.count('{') - stripped.count('}')
                if brace_count <= 0:
                    last_method_end = i + 1
                    in_method = False
        
        if last_method_end > 0:
            return last_method_end
        
        # Strategy 2: Find the last closing brace (end of class)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == '}':
                return i
        
        # Fallback: Insert before the last line
        return len(lines) - 1
    
    def compile_java_project(self) -> Tuple[bool, str]:
        """Compile the Java project to check for syntax errors."""
        try:
            # Try Maven first
            if (self.java_project_path / "pom.xml").exists():
                result = subprocess.run(
                    ["mvn", "compile", "test-compile"],
                    cwd=self.java_project_path,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                return result.returncode == 0, result.stderr
            
            # Try Gradle
            elif (self.java_project_path / "build.gradle").exists() or (self.java_project_path / "build.gradle.kts").exists():
                result = subprocess.run(
                    ["./gradlew", "compileJava", "compileTestJava"],
                    cwd=self.java_project_path,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                return result.returncode == 0, result.stderr
            
            else:
                return False, "No Maven pom.xml or Gradle build file found"
                
        except subprocess.TimeoutExpired:
            return False, "Compilation timeout"
        except Exception as e:
            return False, f"Compilation error: {str(e)}"
    
    def run_specific_test(self, test_class: str, test_method: str) -> Tuple[bool, str]:
        """Run a specific test method."""
        try:
            # Try Maven first
            if (self.java_project_path / "pom.xml").exists():
                test_spec = f"{test_class}#{test_method}"
                command = [
                    "mvn", "clean", "test", 
                    f"-Dtest={test_spec}", 
                    "-DfailIfNoTests=false",
                    "-Dmaven.test.failure.ignore=true",
                    "-Drat.skip=true"
                ]
                result = subprocess.run(
                    command,
                    cwd=self.java_project_path,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                output = result.stdout + result.stderr
                # A successful BUILD is the first gate. Real pass/fail is checked next.
                if "BUILD SUCCESS" not in output:
                    return False, output

                # Check for actual test results
                # Example: Tests run: 1, Failures: 0, Errors: 0
                match = re.search(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+)', output)
                if match:
                    runs, failures, errors = map(int, match.groups())
                    if runs > 0 and failures == 0 and errors == 0:
                        return True, output  # Test ran and passed

                return False, output # Test failed, had errors, or did not run
            
            # Try Gradle
            elif (self.java_project_path / "build.gradle").exists() or (self.java_project_path / "build.gradle.kts").exists():
                test_spec = f"{test_class}.{test_method}"
                result = subprocess.run(
                    ["./gradlew", "test", f"--tests", test_spec],
                    cwd=self.java_project_path,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                return result.returncode == 0, result.stdout + result.stderr
            
            else:
                return False, "No Maven pom.xml or Gradle build file found"
                
        except subprocess.TimeoutExpired:
            return False, "Test execution timeout"
        except Exception as e:
            return False, f"Test execution error: {str(e)}"