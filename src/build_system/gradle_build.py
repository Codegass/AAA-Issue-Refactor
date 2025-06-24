"""Gradle build system implementation."""

import re
import subprocess
from pathlib import Path
from typing import Tuple, Optional, Set, Dict, Any, List
import logging

from .interface import BuildSystem

logger = logging.getLogger('aif')


class GradleBuildSystem(BuildSystem):
    """Gradle build system implementation."""
    
    def __init__(self, project_path: Path):
        """Initialize the Gradle build system."""
        super().__init__(project_path)
        self.scala_modules, self.scala_suffix = self._parse_gradle_config()
    
    def _validate_project(self) -> None:
        """Validate that this is a Gradle project."""
        if not ((self.project_path / "build.gradle").exists() or 
                (self.project_path / "build.gradle.kts").exists()):
            raise ValueError("No build.gradle or build.gradle.kts found - not a Gradle project")
    
    def get_build_system_name(self) -> str:
        """Get the name of this build system."""
        if (self.project_path / "build.gradle.kts").exists():
            return "Gradle (Kotlin DSL)"
        else:
            return "Gradle"
    
    def _parse_gradle_config(self) -> Tuple[Set[str], Optional[str]]:
        """Parses settings.gradle and gradle.properties to find scala modules and suffix."""
        scala_modules = set()
        scala_suffix = None
        
        # Parse settings.gradle for scala module names
        settings_file = self.project_path / "settings.gradle"
        if settings_file.exists():
            try:
                content = settings_file.read_text(encoding='utf-8')
                # This regex is an approximation. A full groovy parser would be more robust.
                match = re.search(r"def scalaModules = \[(.*?)\]", content, re.DOTALL)
                if match:
                    modules_str = match.group(1)
                    # Split by comma and clean up strings
                    raw_modules = modules_str.split(',')
                    for m in raw_modules:
                        cleaned_module = m.strip().strip("'\"")
                        if cleaned_module:
                            scala_modules.add(cleaned_module)
            except Exception as e:
                logger.warning(f"Could not parse scala modules from settings.gradle: {e}")

        # Parse gradle.properties for scala suffix
        properties_file = self.project_path / "gradle.properties"
        if properties_file.exists():
            try:
                content = properties_file.read_text(encoding='utf-8')
                match = re.search(r"^\s*scalaSuffix\s*=\s*(.*)\s*$", content, re.MULTILINE)
                if match:
                    scala_suffix = match.group(1).strip()
            except Exception as e:
                logger.warning(f"Could not parse scala suffix from gradle.properties: {e}")

        return scala_modules, scala_suffix
    
    def compile_project(self) -> Tuple[bool, str]:
        """Compile the Gradle project."""
        debug_logger = logging.getLogger('aif')
        
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_logger.debug(f"Starting Gradle project build...")
            debug_logger.debug(f"Project path: {self.project_path}")
        
        # Override JVM args in command line to avoid modifying user's properties file
        command = [
            "./gradlew", "clean", "compileJava", "compileTestJava",
            "-Dorg.gradle.jvmargs=-Xmx2g"  # Override deprecated MaxPermSize
        ]
        
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_logger.debug(f"Using Gradle command: {' '.join(command)}")
        
        try:
            result = subprocess.run(
                command,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            output = result.stdout + "\n" + result.stderr
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(f"Gradle exit code: {result.returncode}")
                debug_logger.debug(f"Gradle output:\n{output}")
            
            return result.returncode == 0, output
            
        except subprocess.TimeoutExpired:
            error_msg = "Gradle compilation timeout"
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(f"Gradle build process timed out after 300 seconds")
            return False, error_msg
        except Exception as e:
            error_msg = f"Gradle compilation error: {str(e)}"
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(f"Gradle build process exception: {str(e)}")
            return False, error_msg
    
    def run_specific_test(
        self, 
        test_class: str, 
        test_method: str, 
        test_file_path: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """Run a specific test method using Gradle."""
        debug_logger = logging.getLogger('aif')
        
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_logger.debug(f"Running Gradle test: {test_class}.{test_method}")
            debug_logger.debug(f"Project path: {self.project_path}")
            if test_file_path:
                debug_logger.debug(f"Test file path: {test_file_path}")
        
        # For Gradle, we always run from the project root but specify the module task
        test_spec = f"{test_class}.{test_method}"
        
        module_task_path = ""
        if test_file_path:
            try:
                relative_path = test_file_path.relative_to(self.project_path)
                if relative_path.parts:
                    original_module_name = relative_path.parts[0]
                    
                    module_name = original_module_name
                    # Check if it is a scala module and append suffix
                    if self.scala_suffix and original_module_name in self.scala_modules:
                        module_name = f"{original_module_name}_{self.scala_suffix}"
                        if debug_logger.isEnabledFor(logging.DEBUG):
                            debug_logger.debug(f"Module '{original_module_name}' is a Scala module. Using suffixed name: '{module_name}'")
                    
                    # We check existence of the folder using the original name
                    module_dir = self.project_path / original_module_name
                    if module_dir.is_dir() and (module_dir / 'src').is_dir():
                        module_task_path = ":" + module_name
                        if debug_logger.isEnabledFor(logging.DEBUG) and original_module_name == module_name:
                            debug_logger.debug(f"Inferred Gradle module '{module_name}' from test file path.")

            except (ValueError, IndexError):
                if debug_logger.isEnabledFor(logging.DEBUG):
                    debug_logger.debug(f"Could not determine module from path, will attempt to run from root.")
                pass  # module_task_path remains empty

        # If a module was found, prefix the task with the module path.
        # Otherwise, run the task from the root (which may fail for some projects).
        task = f"{module_task_path}:test" if module_task_path else "test"
        
        # Create a temporary init script to filter out deprecated JVM arguments
        # that cause issues on modern JDKs.
        init_script_path = self.project_path / "aif_init.gradle"
        init_script_content = '''
allprojects {
    tasks.withType(Test) {
        // Remove Java 17 incompatible JVM args
        jvmArgs = jvmArgs.findAll { arg ->
            !arg.contains("UseConcMarkSweepGC") &&
            !arg.contains("UseParNewGC") &&
            !arg.contains("CMSIncrementalMode") &&
            !arg.contains("CMSClassUnloadingEnabled") &&
            !arg.contains("MaxPermSize") &&
            !arg.contains("PermSize")
        }
        // Add Java 17 compatible GC if none specified
        if (!jvmArgs.any { it.contains("-XX:+Use") && it.contains("GC") }) {
            jvmArgs += ["-XX:+UseG1GC"]
        }
    }
}
        '''

        java_home_path = None
        try:
            # Find Java 11 home, common on macOS. This is a best-effort approach.
            java_home_cmd = "/usr/libexec/java_home -v 11"
            process = subprocess.run(java_home_cmd, shell=True, capture_output=True, text=True, check=True)
            java_home_path = process.stdout.strip()
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(f"Found Java 11 home at: {java_home_path}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.warning(f"Could not find Java 11 home, continuing with default JDK. Error: {e}")
        
        command = [
            "./gradlew", 
            task,
            "--tests", test_spec,
            "--init-script", init_script_path.name,
            "-Dorg.gradle.jvmargs=-Xmx2g"
        ]

        # If a compatible Java home was found, add it to the command.
        if java_home_path:
            command.append(f"-Dorg.gradle.java.home={java_home_path}")
        
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_logger.debug(f"Using Gradle test command: {' '.join(command)}")
        
        try:
            init_script_path.write_text(init_script_content)

            result = subprocess.run(
                command,
                cwd=self.project_path,  # Always run gradlew from project root
                capture_output=True,
                text=True,
                timeout=300
            )
            
            output = result.stdout + result.stderr
            
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(f"Gradle test exit code: {result.returncode}")
                debug_logger.debug(f"Gradle test output:\n{output}")
            
            # For Gradle, a return code of 0 and "BUILD SUCCESSFUL" indicates success.
            # Gradle's "--tests" filter fails the build if no tests are found.
            return result.returncode == 0 and "BUILD SUCCESSFUL" in output, output
            
        except subprocess.TimeoutExpired:
            error_msg = "Gradle test execution timeout"
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(f"Gradle test execution timed out after 300 seconds")
            return False, error_msg
        except Exception as e:
            error_msg = f"Gradle test execution error: {str(e)}"
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(f"Gradle test execution exception: {str(e)}")
            return False, error_msg
        finally:
            # Ensure the temporary init script is always removed
            if init_script_path.exists():
                init_script_path.unlink()
    
    def find_module_root(self, test_file_path: Path) -> Optional[Path]:
        """Find the Gradle module root directory containing the test file.
        
        For Gradle multi-module projects, individual modules often don't have 
        their own build.gradle files. In such cases, we return the project root
        since Gradle manages all modules from the root directory.
        """
        current_dir = test_file_path.parent
        
        # Walk up the directory tree looking for build.gradle
        while current_dir != current_dir.parent:  # Stop at filesystem root
            if ((current_dir / "build.gradle").exists() or 
                (current_dir / "build.gradle.kts").exists()):
                return current_dir
            current_dir = current_dir.parent
        
        # For Gradle projects without module-specific build files,
        # return the project root since that's where the build is managed
        return self.project_path
    
    def get_configuration(self) -> Dict[str, Any]:
        """Get Gradle-specific configuration."""
        return {
            "scala_modules": list(self.scala_modules),
            "scala_suffix": self.scala_suffix,
            "project_path": str(self.project_path)
        }
    
    def clean_project(self) -> Tuple[bool, str]:
        """Clean the Gradle project."""
        gradle_cmd = self._get_gradle_command()
        command = [gradle_cmd, "clean", "--quiet"]
        
        try:
            result = subprocess.run(
                command,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            output = result.stdout + result.stderr
            return result.returncode == 0, output
            
        except subprocess.TimeoutExpired:
            return False, "Gradle clean timeout"
        except Exception as e:
            return False, f"Gradle clean error: {str(e)}"
    
    def is_project_built(self) -> bool:
        """Check if the Gradle project has been successfully built using multiple criteria."""
        debug_logger = logging.getLogger('aif')
        
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_logger.debug("Checking if Gradle project is built...")
        
        # Multi-level detection
        compiled_classes_check = self.check_compiled_classes()
        dependencies_check = self.check_dependencies_resolved()
        test_accessible_check = self._check_test_classes_accessible()
        
        # If compiled classes exist and test classes are accessible, 
        # we consider the project built even if dependency resolution fails
        # (dependency resolution might fail due to Gradle daemon configuration issues)
        result = compiled_classes_check and test_accessible_check
        
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_logger.debug(f"Build detection result: {result}")
            debug_logger.debug(f"Individual checks: compiled_classes={compiled_classes_check}, "
                             f"dependencies={dependencies_check}, test_accessible={test_accessible_check}")
            if not dependencies_check:
                debug_logger.debug("Note: Dependency check failed, but proceeding based on compiled classes")
        
        return result
    
    def check_compiled_classes(self) -> bool:
        """Check if compiled classes exist in build directories."""
        debug_logger = logging.getLogger('aif')
        
        # For multi-module projects, check all modules
        if self._is_multi_module_gradle():
            return self._check_all_modules_compiled()
        
        # For single module projects
        main_classes = self.project_path / "build" / "classes" / "java" / "main"
        test_classes = self.project_path / "build" / "classes" / "java" / "test"
        
        main_exists = main_classes.exists() and any(main_classes.rglob("*.class"))
        test_exists = test_classes.exists() and any(test_classes.rglob("*.class"))
        
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_logger.debug(f"Compiled classes check: main={main_exists}, test={test_exists}")
        
        return main_exists and test_exists
    
    def check_dependencies_resolved(self) -> bool:
        """Check if Gradle dependencies are resolved."""
        debug_logger = logging.getLogger('aif')
        
        try:
            gradle_cmd = self._get_gradle_command()
            # Check if dependencies can be resolved
            result = subprocess.run(
                [gradle_cmd, "dependencies", "--quiet", "--configuration", "testRuntimeClasspath"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            success = result.returncode == 0
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(f"Dependency resolution check: {success}")
                if not success:
                    debug_logger.debug(f"Dependency check output: {result.stdout + result.stderr}")
            
            return success
            
        except subprocess.TimeoutExpired:
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug("Dependency check timed out")
            return False
        except Exception as e:
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(f"Dependency check error: {str(e)}")
            return False
    
    def quick_compile_test(self) -> Tuple[bool, str]:
        """Perform a quick compilation test without full build."""
        debug_logger = logging.getLogger('aif')
        
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_logger.debug("Performing quick compile test...")
        
        gradle_cmd = self._get_gradle_command()
        command = [gradle_cmd, "testClasses", "--quiet", "--parallel"]
        
        try:
            result = subprocess.run(
                command,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            success = result.returncode == 0
            output = result.stdout + result.stderr
            
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(f"Quick compile test result: {success}")
                if not success:
                    debug_logger.debug(f"Quick compile output: {output}")
            
            return success, output
            
        except subprocess.TimeoutExpired:
            error_msg = "Quick compilation test timed out"
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Quick compilation test error: {str(e)}"
            if debug_logger.isEnabledFor(logging.DEBUG):
                debug_logger.debug(error_msg)
            return False, error_msg
    
    def incremental_compile(self, modified_files: List[Path]) -> Tuple[bool, str]:
        """
        Perform incremental compilation for modified test files.
        
        Args:
            modified_files: List of modified file paths
            
        Returns:
            Tuple of (success, output_message)
        """
        if not modified_files:
            return True, "No files to compile"
        
        # Group files by module for multi-module projects
        module_files = self._group_files_by_module(modified_files)
        
        overall_success = True
        error_messages = []
        successful_modules = []
        
        gradle_cmd = self._get_gradle_command()
        
        for module_path, files in module_files.items():
            logger.debug(f"Compiling module: {module_path}")
            
            try:
                # Determine module task name
                if module_path == self.project_path:
                    # Root module
                    task_name = "testClasses"
                else:
                    # Sub-module
                    module_name = module_path.relative_to(self.project_path)
                    task_name = f":{module_name}:testClasses"
                
                command = [gradle_cmd, task_name, "--quiet"]
                
                result = subprocess.run(
                    command,
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode == 0:
                    successful_modules.append(module_path.name)
                    logger.debug(f"Successfully compiled module: {module_path}")
                else:
                    overall_success = False
                    error_msg = f"Incremental compilation failed for module {module_path.name}"
                    error_messages.append(error_msg)
                    logger.error(f"{error_msg}\nError output: {result.stderr}")
                    
                    # Check if this is a setup/fixture related error
                    if self._is_fixture_error(result.stderr):
                        logger.info(f"Detected fixture/setup error in {module_path.name}, this may be due to incomplete test setup in refactored code")
                
            except subprocess.TimeoutExpired:
                overall_success = False
                error_msg = f"Compilation timeout for module {module_path.name}"
                error_messages.append(error_msg)
                logger.error(error_msg)
            except Exception as e:
                overall_success = False
                error_msg = f"Compilation error for module {module_path.name}: {str(e)}"
                error_messages.append(error_msg)
                logger.error(error_msg)
        
        if overall_success:
            return True, f"Successfully compiled {len(successful_modules)} modules: {', '.join(successful_modules)}"
        else:
            # Provide detailed error information
            success_info = f"Successful modules: {', '.join(successful_modules)}" if successful_modules else "No modules compiled successfully"
            error_info = "; ".join(error_messages)
            return False, f"{success_info}. Errors: {error_info}"
    
    def _is_fixture_error(self, error_output: str) -> bool:
        """
        Check if the compilation error is likely due to test fixture/setup issues.
        
        Args:
            error_output: The error output from compilation
            
        Returns:
            True if the error appears to be fixture-related
        """
        fixture_indicators = [
            "cannot find symbol",
            "variable sma",
            "variable context", 
            "@Before",
            "setUp",
            "assignNewSma",
            "test setup",
            "fixture",
            "initialization",
            "cannot resolve symbol"
        ]
        
        error_lower = error_output.lower()
        return any(indicator in error_lower for indicator in fixture_indicators)
    
    def can_load_test_class(self, test_class_name: str) -> bool:
        """Check if a test class can be loaded in the current Gradle classpath."""
        debug_logger = logging.getLogger('aif')
        
        # Check if the class file exists in the compiled test classes
        class_file_path = test_class_name.replace('.', '/') + '.class'
        
        if self._is_multi_module_gradle():
            # Check all modules
            for module_path in self._get_module_paths():
                test_classes_dir = module_path / "build" / "classes" / "java" / "test"
                class_file = test_classes_dir / class_file_path
                if class_file.exists():
                    if debug_logger.isEnabledFor(logging.DEBUG):
                        debug_logger.debug(f"Found test class {test_class_name} in module {module_path}")
                    return True
        else:
            # Check single module
            test_classes_dir = self.project_path / "build" / "classes" / "java" / "test"
            class_file = test_classes_dir / class_file_path
            if class_file.exists():
                if debug_logger.isEnabledFor(logging.DEBUG):
                    debug_logger.debug(f"Found test class {test_class_name}")
                return True
        
        if debug_logger.isEnabledFor(logging.DEBUG):
            debug_logger.debug(f"Test class {test_class_name} not found in classpath")
        return False
    
    def _is_multi_module_gradle(self) -> bool:
        """Check if this is a multi-module Gradle project."""
        settings_file = self.project_path / "settings.gradle"
        if not settings_file.exists():
            settings_file = self.project_path / "settings.gradle.kts"
        
        if not settings_file.exists():
            return False
        
        try:
            content = settings_file.read_text(encoding='utf-8')
            return "include" in content and ("'" in content or '"' in content)
        except Exception:
            return False
    
    def _check_all_modules_compiled(self) -> bool:
        """Check if modules in a multi-module project are compiled.
        
        Returns True if at least some modules with source code are compiled,
        rather than requiring ALL modules to be compiled.
        """
        module_paths = self._get_module_paths()
        modules_with_source = 0
        modules_compiled = 0
        
        for module_path in module_paths:
            main_classes = module_path / "build" / "classes" / "java" / "main"
            test_classes = module_path / "build" / "classes" / "java" / "test"
            
            # Check if module has source files that should be compiled
            src_main = module_path / "src" / "main" / "java"
            src_test = module_path / "src" / "test" / "java"
            
            has_main_src = src_main.exists() and any(src_main.rglob("*.java"))
            has_test_src = src_test.exists() and any(src_test.rglob("*.java"))
            
            # If module has any source files, count it
            if has_main_src or has_test_src:
                modules_with_source += 1
                
                # Check if at least one type of classes is compiled when source exists
                main_compiled = not has_main_src or (main_classes.exists() and any(main_classes.rglob("*.class")))
                test_compiled = not has_test_src or (test_classes.exists() and any(test_classes.rglob("*.class")))
                
                if main_compiled and test_compiled:
                    modules_compiled += 1
        
        # Return True if at least 50% of modules with source are compiled
        # or if we have a reasonable number of compiled modules
        if modules_with_source == 0:
            return False
        
        compilation_ratio = modules_compiled / modules_with_source
        return compilation_ratio >= 0.5 or modules_compiled >= 5
    
    def _get_module_paths(self) -> List[Path]:
        """Get all module paths in a multi-module Gradle project."""
        module_paths = []
        
        # Always include root module
        module_paths.append(self.project_path)
        
        settings_file = self.project_path / "settings.gradle"
        if not settings_file.exists():
            settings_file = self.project_path / "settings.gradle.kts"
        
        if not settings_file.exists():
            return module_paths
        
        try:
            content = settings_file.read_text(encoding='utf-8')
            # Simple regex to find module names (could be improved)
            import re
            
            # Match both single quotes and double quotes in include statements
            include_pattern = r'include\s*["\']([^"\']+)["\']'
            modules = re.findall(include_pattern, content)
            
            # Also look for include with backslash continuation
            include_backslash_pattern = r'include\s*\\[\s\n]*["\']([^"\']+)["\']'
            modules.extend(re.findall(include_backslash_pattern, content, re.MULTILINE))
            
            for module in modules:
                # Handle both ':module' and 'module' formats
                module_name = module.strip().lstrip(':')
                module_path = self.project_path / module_name
                if module_path.exists():
                    module_paths.append(module_path)
            
            # For projects like Samza that might have dynamic module discovery
            # Also scan for actual directories that look like modules
            for item in self.project_path.iterdir():
                if (item.is_dir() and 
                    item.name.startswith(('samza-', 'kafka-', 'spark-')) and  # Common prefixes
                    (item / "src").exists() and
                    item not in module_paths):
                    module_paths.append(item)
                    
        except Exception:
            pass
        
        return module_paths
    
    def _check_test_classes_accessible(self) -> bool:
        """Check if test classes are accessible (simplified implementation)."""
        if self._is_multi_module_gradle():
            module_paths = self._get_module_paths()
            for module_path in module_paths:
                test_classes_dir = module_path / "build" / "classes" / "java" / "test"
                if test_classes_dir.exists() and any(test_classes_dir.rglob("*.class")):
                    return True
        else:
            test_classes_dir = self.project_path / "build" / "classes" / "java" / "test"
            return test_classes_dir.exists() and any(test_classes_dir.rglob("*.class"))
        
        return False
    
    def _group_files_by_module(self, modified_files: List[Path]) -> dict:
        """Group modified files by their Gradle module."""
        module_files = {}
        
        for file_path in modified_files:
            module_path = self.find_module_root(file_path)
            if module_path not in module_files:
                module_files[module_path] = []
            module_files[module_path].append(file_path)
        
        return module_files

    def _get_gradle_command(self) -> str:
        """Get the Gradle command to use based on the project type."""
        if (self.project_path / "build.gradle.kts").exists():
            return "./gradlew"
        else:
            return "./gradlew" 