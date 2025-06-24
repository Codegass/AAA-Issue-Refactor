"""Smart build management with hybrid mode support."""

import logging
import time
from pathlib import Path
from typing import Tuple, Optional, List
from .interface import BuildSystem

logger = logging.getLogger('aif')

class SmartBuildManager:
    """Manages intelligent build detection and user interaction for complex projects."""
    
    def __init__(self, build_system: BuildSystem):
        self.build_system = build_system
        self.project_path = build_system.project_path
    
    def ensure_project_built(
        self, 
        skip_build: bool = False,
        fallback_manual: bool = True,
        timeout: int = 600
    ) -> Tuple[bool, str]:
        """
        Ensure the project is properly built using hybrid approach.
        
        Args:
            skip_build: Skip automatic build attempt
            fallback_manual: Allow manual build fallback if auto-build fails
            timeout: Maximum time to wait for auto-build
            
        Returns:
            Tuple of (success, message)
        """
        if skip_build:
            logger.info("Skipping automatic build as requested")
            return self._check_build_status()
        
        # Step 1: Check if already built
        if self.build_system.is_project_built():
            logger.info("✓ Project is already built and ready")
            return True, "Project is already built"
        
        # Step 2: Attempt automatic build
        logger.info("Project not detected as built. Attempting automatic build...")
        auto_build_success, auto_build_output = self._attempt_auto_build(timeout)
        
        if auto_build_success:
            logger.info("✓ Automatic build completed successfully")
            return True, "Automatic build successful"
        
        # Step 3: Handle build failure
        logger.warning("❌ Automatic build failed")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Auto-build output: {auto_build_output}")
        
        if not fallback_manual:
            return False, f"Automatic build failed: {auto_build_output}"
        
        # Step 4: Prompt for manual build
        return self._handle_manual_build_fallback(auto_build_output)
    
    def ensure_execution_ready(self, modified_files: List[Path]) -> Tuple[bool, str]:
        """
        Ensure the project is ready for execution testing with incremental compilation.
        
        Args:
            modified_files: List of files that have been modified and need compilation
            
        Returns:
            Tuple of (success, message)
        """
        # Step 1: Check basic build status
        if not self.build_system.is_project_built():
            return False, (
                "Project is not properly built. Please run discovery phase first or "
                "manually build the project using your preferred IDE."
            )
        
        # Step 2: Perform incremental compilation for modified files
        if modified_files:
            logger.info(f"Performing incremental compilation for {len(modified_files)} modified files...")
            
            compile_success, compile_output = self.build_system.incremental_compile(modified_files)
            
            if not compile_success:
                logger.error("❌ Incremental compilation failed")
                return False, self._format_compile_error_message(compile_output)
            
            logger.info("✓ Incremental compilation successful")
        
        return True, "Project ready for execution testing"
    
    def _attempt_auto_build(self, timeout: int) -> Tuple[bool, str]:
        """Attempt automatic project build with timeout."""
        logger.info(f"Starting automatic build (timeout: {timeout}s)...")
        
        try:
            # First try a quick compile test
            quick_success, quick_output = self.build_system.quick_compile_test()
            if quick_success:
                logger.info("✓ Quick compilation test passed")
                # Verify the build is actually complete
                if self.build_system.is_project_built():
                    return True, "Quick build successful"
            
            # If quick test fails or build is incomplete, try full build
            logger.info("Attempting full project build...")
            build_success, build_output = self.build_system.compile_project()
            
            if build_success and self.build_system.is_project_built():
                return True, "Full build successful"
            else:
                return False, build_output
                
        except Exception as e:
            error_msg = f"Build process exception: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def _check_build_status(self) -> Tuple[bool, str]:
        """Check if the project is properly built."""
        if self.build_system.is_project_built():
            logger.info("✓ Project build status verified")
            return True, "Project is properly built"
        else:
            logger.error("❌ Project is not properly built")
            return False, (
                "Project is not properly built. Please build the project manually "
                "using your preferred IDE or build tool, then try again."
            )
    
    def _handle_manual_build_fallback(self, auto_build_output: str) -> Tuple[bool, str]:
        """Handle manual build fallback with user interaction."""
        
        # Display helpful error message and instructions
        self._display_manual_build_prompt(auto_build_output)
        
        # Wait for user confirmation
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                user_input = input().strip().lower()
                
                if user_input in ['', 'y', 'yes', 'continue']:
                    # Check if build is now complete
                    if self.build_system.is_project_built():
                        logger.info("✓ Project build detected after manual intervention")
                        return True, "Manual build successful"
                    else:
                        remaining = max_attempts - attempt - 1
                        if remaining > 0:
                            print(f"❌ Build not detected. Please ensure compilation is complete. "
                                f"({remaining} attempts remaining)")
                            print("Press Enter when build is complete...")
                        else:
                            print("❌ Build still not detected after maximum attempts.")
                            return False, "Manual build verification failed"
                
                elif user_input in ['n', 'no', 'skip']:
                    print("⚠ Continuing without proper build verification...")
                    return False, "User chose to skip build verification"
                
                elif user_input in ['q', 'quit', 'exit']:
                    print("🛑 Operation cancelled by user")
                    return False, "Operation cancelled by user"
                
                else:
                    print("Please enter 'y' to continue, 'n' to skip, or 'q' to quit:")
                    
            except KeyboardInterrupt:
                print("\n🛑 Operation cancelled by user")
                return False, "Operation cancelled by user"
            except EOFError:
                print("\n❌ Input stream ended unexpectedly")
                return False, "Input stream ended"
        
        return False, "Manual build verification failed after maximum attempts"
    
    def _display_manual_build_prompt(self, auto_build_output: str):
        """Display user-friendly manual build instructions."""
        
        build_system_name = self.build_system.get_build_system_name()
        
        print("\n" + "="*70)
        print("🔧 MANUAL BUILD REQUIRED")
        print("="*70)
        print("❌ Automatic build failed. Please build the project manually.")
        print()
        print(f"📁 Project Path: {self.project_path}")
        print(f"🛠  Build System: {build_system_name}")
        print()
        print("💡 Recommended approaches:")
        print()
        print("1. 🎯 Using IntelliJ IDEA (Recommended):")
        print("   • Open the project in IntelliJ IDEA")
        print("   • Go to Build → Build Project")
        print("   • Ensure no compilation errors exist")
        print()
        print("2. ⌨️  Using Command Line:")
        
        if build_system_name == "Maven":
            print("   mvn clean compile test-compile")
        elif build_system_name == "Gradle":
            print("   ./gradlew build testClasses")
        else:
            print("   Use your build system's compile command")
        
        print()
        print("3. 🔧 Using Other IDEs:")
        print("   • Eclipse: Project → Clean → Build")
        print("   • VS Code: Use Java extension build features")
        print()
        
        # Show build error details in debug mode
        if logger.isEnabledFor(logging.DEBUG):
            print("🐛 Debug - Build Error Details:")
            print("-" * 50)
            print(auto_build_output[:1000] + ("..." if len(auto_build_output) > 1000 else ""))
            print("-" * 50)
            print()
        
        print("✅ After completing the build, press Enter to continue...")
        print("   (or type 'n' to skip, 'q' to quit)")
        print("="*70)
    
    def _format_compile_error_message(self, compile_output: str) -> str:
        """Format compilation error message with helpful suggestions."""
        
        error_message = "Incremental compilation failed.\n\n"
        
        # Analyze common error patterns
        if "package does not exist" in compile_output:
            error_message += "🔍 Detected Issue: Missing package imports\n"
            error_message += "💡 Suggestions:\n"
            error_message += "   • Check if required imports were added correctly\n"
            error_message += "   • Verify all dependencies are available\n"
            error_message += "   • Try rebuilding the entire project\n\n"
        
        elif "cannot find symbol" in compile_output:
            error_message += "🔍 Detected Issue: Symbol resolution problems\n"
            error_message += "💡 Suggestions:\n"
            error_message += "   • Check method names and class references\n"
            error_message += "   • Verify imports for custom classes\n"
            error_message += "   • Ensure all dependencies are compiled\n\n"
        
        elif "syntax error" in compile_output.lower():
            error_message += "🔍 Detected Issue: Syntax errors in generated code\n"
            error_message += "💡 Suggestions:\n"
            error_message += "   • Review the refactored code for syntax issues\n"
            error_message += "   • Check bracket and parenthesis matching\n"
            error_message += "   • Verify all statements end with semicolons\n\n"
        
        else:
            error_message += "🔍 Compilation failed for unknown reasons\n"
            error_message += "💡 General suggestions:\n"
            error_message += "   • Try building the project manually in your IDE\n"
            error_message += "   • Check for any project configuration issues\n"
            error_message += "   • Verify all dependencies are properly resolved\n\n"
        
        error_message += "🛠  Recommended Actions:\n"
        error_message += "   1. Open the project in IntelliJ IDEA\n"
        error_message += "   2. Fix any compilation errors shown in the IDE\n"
        error_message += "   3. Re-run the execution test phase\n\n"
        
        # Add detailed error output (always show for compilation errors)
        error_message += "📋 Detailed Error Output:\n"
        error_message += "-" * 50 + "\n"
        error_message += compile_output
        error_message += "\n" + "-" * 50
        
        return error_message 