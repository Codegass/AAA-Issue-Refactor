#!/usr/bin/env python3
"""
AAA Issue Refactor CLI Tool

This tool uses Large Language Models to automatically refactor Java test cases,
eliminating identified AAA (Arrange-Act-Assert) pattern violations while ensuring
the refactored code remains functional.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import pandas as pd
import logging
import csv
import re

from .discovery import TestDiscovery, TestCase
from .refactor import TestRefactor, RefactoringResult, TestContext
from .validator import CodeValidator
from .executor import ResultsRecorder
from .logger import setup_logger
from .utils import BackupManager, check_and_auto_update

logger = logging.getLogger('aif')

def validate_paths(java_project_path: str, data_folder_path: str, output_folder_path: str) -> Tuple[Path, Path, Path]:
    """Validate and return Path objects for input arguments."""
    java_path = Path(java_project_path).resolve()
    data_path = Path(data_folder_path).resolve()
    output_path = Path(output_folder_path).resolve()

    if not java_path.exists():
        raise FileNotFoundError(f"Java project path does not exist: {java_path}")

    if not data_path.exists():
        raise FileNotFoundError(f"Data folder path does not exist: {data_path}")

    # Create output directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)

    return java_path, data_path, output_path


def find_discovery_file(java_project_path: Path, output_path: Path) -> Optional[Path]:
    """
    Auto-discover the discovery results file based on project name.
    Returns the path to <project_name>_AAA_Refactor_Cases.csv if found.
    """
    project_name = java_project_path.name
    discovery_file = output_path / f"{project_name}_AAA_Refactor_Cases.csv"
    
    if discovery_file.exists():
        logger.info(f"Auto-discovered discovery file: {discovery_file}")
        return discovery_file
    
    # Try to find any discovery file in output directory
    discovery_files = list(output_path.glob("*_AAA_Refactor_Cases.csv"))
    if discovery_files:
        discovery_file = discovery_files[0]
        logger.info(f"Found discovery file: {discovery_file}")
        return discovery_file
    
    return None


def discovery_phase(java_project_path: Path, data_folder_path: Path, output_path: Path,
                   skip_initial_build: bool = False, fallback_manual: bool = True, 
                   build_timeout: int = 600) -> Path:
    """Phase 1: Test Discovery & Validation."""
    logger.info("Phase 1: Test Discovery & Validation")
    logger.info("=" * 50)

    discovery = TestDiscovery(java_project_path, data_folder_path)
    logger.info("Loading AAA results from CSV...")
    test_cases = discovery.load_aaa_results()
    logger.info(f"Found {len(test_cases)} initial test cases")

    logger.info("Validating test cases...")
    validated_cases = discovery.validate_test_cases(test_cases, skip_initial_build, fallback_manual, build_timeout)
    runnable_count = sum(1 for tc in validated_cases if tc.runable == "yes")
    logger.info(f"Runnable test cases: {runnable_count}/{len(validated_cases)}")

    logger.info("Saving refactor cases CSV...")
    output_file = discovery.save_refactor_cases_csv(validated_cases, output_path)
    logger.info(f"✓ Discovery results saved to {output_file}")

    return output_file


def load_test_cases_from_csv(input_file: Path) -> List[TestCase]:
    """Load test cases from a specified CSV file."""
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    df = pd.read_csv(input_file)
    df.fillna('', inplace=True)
    test_cases = []
    for _, row in df.iterrows():
        # Handle different column name formats
        project_name = row.get('project_name', row.get('project', ''))
        test_class_name = row.get('test_class_name', row.get('class_name', ''))
        test_method_name = row.get('test_method_name', row.get('test_case_name', ''))
        issue_type = row.get('issue_type', '')
        
        test_case = TestCase(
            project_name=project_name,
            test_class_name=test_class_name,
            test_method_name=test_method_name,
            issue_type=issue_type
        )
        
        # Handle test_path - try to get from CSV or auto-discover
        test_path = row.get('test_path', 'not found')
        if test_path == 'not found' or not test_path:
            # Auto-discover test file path based on class name
            discovered_path = _discover_test_file_path(test_class_name, input_file.parent.parent)
            test_case.test_path = discovered_path if discovered_path else 'not found'
            if discovered_path:
                logger.info(f"Auto-discovered test path: {test_class_name} -> {discovered_path}")
        else:
            test_case.test_path = test_path
            
        test_case.test_case_loc = row.get('test_case_LOC', 0)
        test_case.runable = row.get('runable', 'no')
        test_case.pass_status = row.get('pass', 'no')
        test_cases.append(test_case)
    return test_cases


def _discover_test_file_path(test_class_name: str, search_base: Path) -> Optional[str]:
    """Auto-discover test file path based on class name."""
    if not test_class_name:
        return None
    
    # Convert package.ClassName to path format
    class_path = test_class_name.replace('.', '/') + '.java'
    
    # Common test directory patterns
    test_dirs = [
        'src/test/java',
        'test/java', 
        'src/test',
        'test'
    ]
    
    # Search in parent directories (go up from data folder to find project root)
    search_paths = [search_base, search_base.parent, search_base.parent.parent]
    
    for base_path in search_paths:
        for test_dir in test_dirs:
            potential_path = base_path / test_dir / class_path
            if potential_path.exists():
                return str(potential_path)
    
    return None


def refactoring_phase(test_cases: List[TestCase], java_project_path: Path,
                     data_folder_path: Path, output_path: Path, rftype: str,
                      debug_mode: bool = False) -> None:
    """Phase 2: Test Refactoring. Generates code but does not execute it."""
    logger.info(f"\nPhase 2: Test Refactoring ({rftype.upper()} strategy)")
    logger.info("=" * 50)

    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    refactor = TestRefactor(prompts_dir, data_folder_path, rftype, output_path, java_project_path)
    recorder = ResultsRecorder(output_path)

    # Process ALL test cases regardless of their runnable/pass status from Phase 1
    # Phase 2 focuses purely on code quality improvement, not execution feasibility
    all_cases = test_cases
    
    if rftype == 'testsmell':
        # For testsmell strategy, we need to check which cases have test smells
        # This will be handled in the TestRefactor.refactor_test_case method
        cases_to_refactor = all_cases  # All cases will be checked for test smells
        logger.info(f"Processing {len(all_cases)} test cases (test smell detection will be performed)...")
    else:
        # For AAA and DSL strategies, filter by AAA issue type
        cases_to_refactor = [tc for tc in all_cases if tc.issue_type.lower().strip() != 'good aaa']
        logger.info(f"Processing {len(all_cases)} test cases ({len(cases_to_refactor)} need refactoring)...")

    results = []
    project_name = ""
    if all_cases:
        project_name = all_cases[0].project_name

        for i, test_case in enumerate(all_cases, 1):
            logger.info(f"\n[{i}/{len(all_cases)}] Processing: {test_case.test_class_name}.{test_case.test_method_name}")
            
            if rftype == 'testsmell':
                # For testsmell strategy, show test smell information if available
                if hasattr(refactor, '_get_test_smell_types'):
                    test_smell_types = refactor._get_test_smell_types(test_case.test_class_name, test_case.test_method_name)
                    if test_smell_types:
                        logger.info(f"Test Smell Types: {', '.join(test_smell_types)}")
                    else:
                        logger.info("Test Smell Types: None found")
            else:
                # For AAA/DSL strategies, show AAA issue type
                logger.info(f"Issue Type: {test_case.issue_type}")

            original_code = ""
            original_imports = []
            try:
                context = refactor.load_test_context(
                    test_case.project_name, test_case.test_class_name, test_case.test_method_name
                )
                original_code = context.test_case_source_code
                original_imports = context.imported_packages

                if rftype != 'testsmell' and test_case.issue_type.lower().strip() == 'good aaa':
                    logger.info("  ✓ Skipping: No refactoring needed.")
                    refactoring_result = RefactoringResult(
                        success=True, refactored_code=original_code, error_message="Skipped: Good AAA"
                    )
                else:
                    logger.info("  Refactoring...")
                    refactoring_result = refactor.refactor_test_case(test_case, rftype=rftype, debug_mode=debug_mode)

                if refactoring_result.success:
                    logger.info(f"  ✓ Refactoring successful ({refactoring_result.iterations} iterations)")
                else:
                    logger.error(f"  ✗ Refactoring failed: {refactoring_result.error_message}")

                result_record = recorder.create_result_record(
                    test_case, original_code, original_imports, refactoring_result, rftype
                )
                results.append(result_record)

            except Exception as e:
                logger.error(f"  ✗ Error processing test case: {str(e)}", exc_info=debug_mode)
                error_result = RefactoringResult(success=False, error_message=str(e))
                result_record = recorder.create_result_record(
                    test_case, original_code, original_imports, error_result, rftype
                )
                results.append(result_record)

    if results:
        output_file = recorder.save_results(project_name, rftype, results)
        logger.info(f"\n✓ Refactoring results for '{rftype}' strategy saved to {output_file}")
        
        # Save usage statistics
        if refactor.usage_tracker:
            usage_file = refactor.usage_tracker.save_usage_statistics(project_name)
            if usage_file:
                logger.info(f"✓ Usage statistics saved to {usage_file}")
                # Log summary
                stats = refactor.usage_tracker.get_summary_stats()
                if stats:
                    logger.info(f"✓ Summary: {stats['successful_cases']}/{stats['total_cases']} successful, "
                               f"${stats['total_cost']:.4f} total cost, {stats['total_time']:.2f}s total time")


def execution_test_phase(java_project_path: Path, output_path: Path, 
                         debug_mode: bool = False, keep_files: bool = False,
                         fallback_manual: bool = True, skip_initial_build: bool = False) -> None:
    """Phase 3: Execution Testing. Integrates and tests all refactored code."""
    logger.info("\nPhase 3: Execution Testing")
    logger.info("=" * 50)
    
    # Clean any existing refactored code before starting
    logger.info("Cleaning any existing refactored code before execution testing...")
    clean_refactored_phase(java_project_path, debug_mode)
    
    # Discover project name from result files
    result_files = list(output_path.glob("*_refactored_result.csv"))
    if not result_files:
        logger.warning("No refactoring result files found. Skipping execution phase.")
        return
    
    # Try to match the result file with the Java project name
    java_project_name = java_project_path.name
    target_result_file = output_path / f"{java_project_name}_refactored_result.csv"
    
    if target_result_file.exists():
        results_file = target_result_file
        project_name = java_project_name
        logger.info(f"Found matching results file for project '{project_name}': {results_file}")
    else:
        # Fallback to first available file if exact match not found
        results_file = result_files[0]
        project_name = results_file.stem.replace("_refactored_result", "")
        logger.warning(f"No exact match found for project '{java_project_name}', using: {results_file}")
        logger.info(f"Available result files: {[f.name for f in result_files]}")

    df = pd.read_csv(results_file)
    df.fillna('', inplace=True)
    
    validator = CodeValidator(java_project_path)
    recorder = ResultsRecorder(output_path)
    backup_mgr = BackupManager()

    # Import and create build manager
    from .build_system import SmartBuildManager
    build_manager = SmartBuildManager(validator.build_system)

    # Get a unique list of all test files to back them up once
    all_test_paths = {p for p in df['test_path'].unique() if p and Path(p).exists()}
    backup_mgr.backup([Path(p) for p in all_test_paths])

    # Initialize execution summary tracking
    execution_summary = {
        'total_strategies': 0,
        'strategies_with_tests': 0,
        'failed_compilation_modules': set(),
        'compilation_failures': [],
        'test_failures': [],
        'successful_tests': [],
        'total_tests_run': 0
    }

    try:
        for strategy in recorder.STRATEGY_MAPPING.keys():
            prefix = recorder.STRATEGY_MAPPING[strategy]
            code_col = f'{prefix}_refactored_test_case_code'
            error_col = f'{prefix}_refactoring_error'
            result_col = f'{prefix}_refactored_test_case_result'
            
            execution_summary['total_strategies'] += 1
            
            if code_col not in df.columns:
                continue

            logger.info(f"\n--- Testing Strategy: {strategy.upper()} ---")
            
            # Filter for rows that have successful refactorings for this strategy
            strategy_df = df[(df[code_col] != '') & (df[error_col] == '')].copy()
            if strategy_df.empty:
                logger.info("No successful refactorings to test for this strategy.")
                continue

            execution_summary['strategies_with_tests'] += 1

            # Collect all files that will be modified for incremental compilation
            modified_files = []
            for _, row in strategy_df.iterrows():
                test_path = Path(row['test_path'])
                if test_path.exists():
                    modified_files.append(test_path)

            # Check if Hamcrest dependency is needed for this strategy
            hamcrest_needed = any('hamcrest' in str(row.get(f'{prefix}_refactored_test_case_imports', '')).lower() 
                                for _, row in strategy_df.iterrows())
            
            if hamcrest_needed:
                logger.info("Detecting Hamcrest usage, ensuring dependency is available...")
                hamcrest_success, hamcrest_message = validator.ensure_hamcrest_dependency()
                if hamcrest_success:
                    logger.info(f"✓ Hamcrest dependency ready: {hamcrest_message}")
                else:
                    logger.warning(f"⚠ Hamcrest dependency issue: {hamcrest_message}")

            # Always ensure execution readiness with smart build management
            logger.info("Verifying execution readiness...")
            exec_ready, exec_message = build_manager.ensure_execution_ready(
                modified_files, skip_build_check=skip_initial_build
            )
            
            if not exec_ready:
                logger.error(f"❌ Execution preparation failed: {exec_message}")
                logger.error("Please resolve build issues and try again.")
                
                # Track compilation failures
                if "compilation failed" in exec_message.lower():
                    failed_modules = [msg.split("module ")[-1].split()[0] for msg in exec_message.split(";") 
                                    if "compilation failed for module" in msg]
                    execution_summary['failed_compilation_modules'].update(failed_modules)
                
                continue
            
            logger.info(f"✓ Execution environment ready: {exec_message}")

            for _, row in strategy_df.iterrows():
                test_path = Path(row['test_path'])
                test_full_name = f"{row['test_class_name']}.{row['test_method_name']}"
                logger.info(f"Testing {test_full_name}...")
                execution_summary['total_tests_run'] += 1
                
                # Skip tests with invalid file paths
                if not test_path.exists() or str(test_path) == "not found":
                    logger.warning(f"  ✗ Test file not found: {test_path}")
                    df.loc[df.index == row.name, result_col] = "file_not_found"
                    execution_summary['test_failures'].append({
                        'strategy': strategy,
                        'test': test_full_name,
                        'reason': 'Test file not found'
                    })
                    continue
                
                # We need to re-integrate code for each test, as previous integrations are reverted
                # This is inefficient but safe. A better way would be to group by file.
                # For now, we restore, modify, test, and move to the next.
                backup_mgr.restore_file(test_path)
                
                # Extract method names from refactored code to handle mismatches
                refactored_method_names = _extract_method_names_from_code(row[code_col])
                csv_method_name = row['test_method_name']
                
                # Determine which method to comment out/delete
                target_method_for_removal = csv_method_name
                if refactored_method_names:
                    # Check if any refactored method conflicts with existing methods
                    with open(test_path, 'r', encoding='utf-8') as f:
                        original_content = f.read()
                    original_method_names = _extract_method_names_from_code(original_content)
                    
                    # For testsmell strategy, handle method name conflicts more intelligently
                    if strategy == 'testsmell':
                        method_conflicts = []
                        for ref_method in refactored_method_names:
                            if ref_method in original_method_names:
                                method_conflicts.append(ref_method)
                        
                        if method_conflicts:
                            logger.info(f"  ⚠️ Testsmell method name conflicts detected: {', '.join(method_conflicts)}")
                            logger.info(f"  🔄 Will remove original method '{csv_method_name}' to avoid conflicts")
                            # For testsmell, always remove the original method when there are conflicts
                            target_method_for_removal = csv_method_name
                    else:
                        # Original logic for AAA/DSL strategies
                        for ref_method in refactored_method_names:
                            if ref_method in original_method_names and ref_method != csv_method_name:
                                # Found a conflict - we should remove the conflicting method instead
                                target_method_for_removal = ref_method
                                logger.info(f"  📝 Method name mismatch detected:")
                                logger.info(f"     CSV method: {csv_method_name}")
                                logger.info(f"     Refactored method: {ref_method}")
                                logger.info(f"     Will comment out: {target_method_for_removal}")
                                break
                
                # Integrate the code
                # Determine if this is one-to-many refactoring based on strategy and method count
                if strategy == 'testsmell':
                    # For testsmell strategy, check if we have multiple refactored methods
                    num_refactored_methods = len(refactored_method_names) if refactored_method_names else 0
                    is_one_to_many = num_refactored_methods > 1
                    
                    # Special handling for test smells that typically create multiple methods
                    if row.get('issue_type', '').lower() in ['eager test', 'multiple acts', 'conditional test logic']:
                        is_one_to_many = True
                        
                    logger.info(f"  📊 Testsmell strategy: {num_refactored_methods} methods generated, one-to-many: {is_one_to_many}")
                else:
                    # For AAA and DSL strategies, use the original logic
                    is_one_to_many = row['issue_type'].lower().strip() == "multiple aaa"
                # Parse additional imports, filtering out empty strings
                imports_str = row[f'{prefix}_refactored_test_case_imports']
                raw_imports = [imp.strip() for imp in imports_str.split(',') if imp.strip()] if imports_str else []
                
                # Use SmartImportManager for all import processing
                from .import_manager import SmartImportManager
                import_manager = SmartImportManager(java_project_path)
                
                # Read file content once for all operations
                original_content = test_path.read_text(encoding='utf-8')
                
                # Use SmartImportManager to normalize and validate imports
                additional_imports = []
                for imp in raw_imports:
                    normalized = import_manager._normalize_import_format(imp, original_content)
                    if normalized:  # Only add if normalization succeeded (filters out comments, etc.)
                        additional_imports.append(normalized)
                
                # For DSL strategy, also detect missing imports automatically
                if strategy == 'dsl':
                    # Analyze the refactored code for missing imports
                    existing_imports = set()
                    # Convert additional_imports to proper format for checking
                    for imp in additional_imports:
                        if imp.startswith('static '):
                            existing_imports.add(f"import {imp};")
                        else:
                            existing_imports.add(f"import {imp};")
                    
                    requirements = import_manager.analyze_code_requirements(row[code_col], existing_imports)
                    
                    # Add any missing imports detected by the smart manager
                    for req in requirements:
                        import_stmt = req.import_statement
                        # Ensure proper format for additional_imports list
                        if import_stmt.startswith('import '):
                            import_stmt = import_stmt[7:]  # Remove 'import '
                        if import_stmt.endswith(';'):
                            import_stmt = import_stmt[:-1]  # Remove ';'
                            
                        # Only add if not already present
                        if import_stmt not in additional_imports:
                            additional_imports.append(import_stmt)
                            logger.info(f"  📦 Auto-detected missing import: {import_stmt} ({req.reason})")
                
                # CRITICAL: Analyze all imports to determine required dependencies BEFORE integration
                if additional_imports:
                    logger.info(f"  🔍 Analyzing {len(additional_imports)} imports for dependency requirements...")
                    
                    # Use SmartImportManager to analyze third-party dependencies
                    third_party_deps_needed = import_manager.analyze_third_party_dependencies(additional_imports)
                    
                    # Also analyze production imports for potential issues
                    production_analysis = import_manager.analyze_production_imports(additional_imports, original_content)
                    if production_analysis['recommendations']:
                        for recommendation in production_analysis['recommendations']:
                            logger.warning(f"  ⚠ Production import analysis: {recommendation}")
                    
                    # Add required dependencies before proceeding
                    for dep in third_party_deps_needed:
                        logger.info(f"  📚 Detected {dep['type'].upper()} usage, ensuring dependency is available...")
                        logger.debug(f"    Required imports: {', '.join(dep['imports'])}")
                        
                        if dep['type'] == 'hamcrest':
                            hamcrest_success, hamcrest_message = validator.ensure_hamcrest_dependency()
                            if hamcrest_success:
                                logger.info(f"  ✓ {dep['type'].upper()} dependency ready: {hamcrest_message}")
                            else:
                                logger.error(f"  ❌ {dep['type'].upper()} dependency failed: {hamcrest_message}")
                                df.loc[df.index == row.name, result_col] = "dependency_failed"
                                execution_summary['test_failures'].append({
                                    'strategy': strategy,
                                    'test': test_full_name,
                                    'reason': f'{dep["type"].title()} dependency failed: {hamcrest_message}'
                                })
                                continue  # Skip this test case
                        # TODO: Add handling for other dependency types (mockito, etc.)
                        else:
                            logger.warning(f"  ⚠ Unknown dependency type '{dep['type']}', skipping dependency check")
                
                # Use SmartImportManager for import integration
                
                # Add imports using SmartImportManager
                if additional_imports:
                    modified_content, import_success = import_manager.add_missing_imports(original_content, additional_imports)
                    if not import_success:
                        logger.warning(f"  ⚠ Import integration had issues for {row['test_method_name']}")
                else:
                    modified_content = original_content
                
                # Now integrate the code using the validator
                success, final_content, _ = validator.integrate_refactored_method(
                    test_path, target_method_for_removal, row[code_col], strategy,
                    [], is_one_to_many,  # Pass empty imports since we already handled them
                    debug_mode=debug_mode
                )
                
                if success:
                    # Use our content with proper imports
                    lines = final_content.split('\n')
                    original_lines = modified_content.split('\n')
                    
                    # Find the imports section in both contents
                    final_import_end = -1
                    original_import_end = -1
                    
                    for i, line in enumerate(lines):
                        if line.strip().startswith('import '):
                            final_import_end = i
                    
                    for i, line in enumerate(original_lines):
                        if line.strip().startswith('import '):
                            original_import_end = i
                    
                    # Replace the imports section in final_content with our properly managed imports
                    if final_import_end >= 0 and original_import_end >= 0:
                        # Keep the package and imports from our managed content
                        final_content = '\n'.join(original_lines[:original_import_end + 1] + lines[final_import_end + 1:])
                    
                    modified_content = final_content
                
                if not success:
                    logger.warning(f"  ✗ Code integration failed for {row['test_method_name']}.")
                    df.loc[df.index == row.name, result_col] = "integration_failed"
                    execution_summary['test_failures'].append({
                        'strategy': strategy,
                        'test': test_full_name,
                        'reason': 'Code integration failed'
                    })
                    continue

                test_path.write_text(modified_content, encoding='utf-8')
                
                # Always perform incremental compilation for quality assurance
                compile_success, compile_output = build_manager.build_system.incremental_compile([test_path])
                if not compile_success:
                        logger.warning(f"  ✗ Incremental compilation failed for {row['test_method_name']}.")
                        logger.error(f"Compilation error details:\n{compile_output}")
                        df.loc[df.index == row.name, result_col] = "compilation_failed"
                        execution_summary['test_failures'].append({
                            'strategy': strategy,
                            'test': test_full_name,
                            'reason': 'Incremental compilation failed'
                        })
                        
                        # Extract module name from test path for better error tracking
                        module_name = "unknown"
                        for part in test_path.parts:
                            if part in ['core', 'plugins'] or 'struts' in part or 'tiles' in part or 'samza' in part:
                                module_name = part
                                break
                        execution_summary['failed_compilation_modules'].add(module_name)
                        
                        continue
                
                # Discover test methods to run from the result CSV
                method_names_col = f'{prefix}_refactored_method_names'
                if method_names_col in row and row[method_names_col]:
                    refactored_methods = [method.strip() for method in row[method_names_col].split(',') if method.strip()]
                else:
                    refactored_methods = []

                if not refactored_methods:
                    logger.warning(f"  Could not find any refactored method names in result file.")
                    df.loc[df.index == row.name, result_col] = "no_test_found"
                    execution_summary['test_failures'].append({
                        'strategy': strategy,
                        'test': test_full_name,
                        'reason': 'No refactored methods found'
                    })
                    continue

                # Verify that the refactored methods actually exist in the integrated code
                current_file_content = test_path.read_text(encoding='utf-8')
                existing_methods_in_file = _extract_method_names_from_code(current_file_content)
                
                # Check which methods actually exist
                found_methods = []
                missing_methods = []
                for method in refactored_methods:
                    if method in existing_methods_in_file:
                        found_methods.append(method)
                    else:
                        missing_methods.append(method)
                        
                if missing_methods:
                    logger.warning(f"  ⚠ Methods not found in integrated file: {', '.join(missing_methods)}")
                    
                if not found_methods:
                    logger.error(f"  ✗ None of the refactored methods exist in the integrated file.")
                    logger.error(f"    Expected: {', '.join(refactored_methods)}")
                    logger.error(f"    Found methods: {', '.join(existing_methods_in_file)}")
                    df.loc[df.index == row.name, result_col] = "method_not_found"
                    execution_summary['test_failures'].append({
                        'strategy': strategy,
                        'test': test_full_name,
                        'reason': f'Refactored methods not found in file: {", ".join(missing_methods)}'
                    })
                    continue

                logger.info(f"  Running refactored test(s): {', '.join(found_methods)}")
                if missing_methods:
                    logger.info(f"  Skipping missing methods: {', '.join(missing_methods)}")
                    
                all_passed = True
                failed_methods = []
                for method in found_methods:
                    passed, output = validator.run_specific_test(row['test_class_name'], method, test_path)
                    if not passed:
                        all_passed = False
                        failed_methods.append(method)
                        logger.warning(f"  - Method '{method}' FAILED.")
                        if debug_mode: logger.debug(f"Test output:\n{output}")
                        # Continue to test other methods even if one fails
                
                test_result = "pass" if all_passed else "fail"
                result_detail = test_result
                if missing_methods:
                    result_detail += f" (missing: {len(missing_methods)})"
                if failed_methods:
                    result_detail += f" (failed: {', '.join(failed_methods)})"
                    
                logger.info(f"  ✓ Test result: {result_detail.upper()}")
                df.loc[df.index == row.name, result_col] = test_result
                
                if all_passed and not missing_methods:
                    execution_summary['successful_tests'].append({
                        'strategy': strategy,
                        'test': test_full_name,
                        'methods': found_methods
                    })
                else:
                    failure_reason = []
                    if failed_methods:
                        failure_reason.append(f'Failed methods: {", ".join(failed_methods)}')
                    if missing_methods:
                        failure_reason.append(f'Missing methods: {", ".join(missing_methods)}')
                    
                    execution_summary['test_failures'].append({
                        'strategy': strategy,
                        'test': test_full_name,
                        'reason': '; '.join(failure_reason)
                    })
        
        # After all strategies are tested, save the final, updated dataframe
        df.to_csv(results_file, index=False, quoting=csv.QUOTE_ALL)
        logger.info(f"\n✓ Execution results saved to {results_file}")

    finally:
        if not keep_files:
            logger.info("Restoring all original files...")
            backup_mgr.restore_all()
        backup_mgr.cleanup()
        
        # Clean up any dependency changes made during validation
        if 'validator' in locals():
            validator.cleanup_dependency_changes()

    # Display execution summary
    _display_execution_summary(execution_summary, project_name)


def _display_execution_summary(summary: dict, project_name: str) -> None:
    """Display a comprehensive execution summary."""
    logger.info("\n" + "=" * 60)
    logger.info(f"EXECUTION SUMMARY FOR PROJECT: {project_name.upper()}")
    logger.info("=" * 60)
    
    # Overall statistics
    logger.info(f"📊 Overall Statistics:")
    logger.info(f"   • Total strategies available: {summary['total_strategies']}")
    logger.info(f"   • Strategies with tests: {summary['strategies_with_tests']}")
    logger.info(f"   • Total tests attempted: {summary['total_tests_run']}")
    logger.info(f"   • Successful tests: {len(summary['successful_tests'])}")
    logger.info(f"   • Failed tests: {len(summary['test_failures'])}")
    
    # Compilation failures
    if summary['failed_compilation_modules']:
        logger.info(f"\n❌ Failed Compilation Modules:")
        for module in sorted(summary['failed_compilation_modules']):
            logger.info(f"   • {module}")
    else:
        logger.info(f"\n✅ No compilation failures detected")
    
    # Test failures breakdown
    if summary['test_failures']:
        logger.info(f"\n❌ Failed Test Cases:")
        failure_by_reason = {}
        for failure in summary['test_failures']:
            reason = failure['reason']
            if reason not in failure_by_reason:
                failure_by_reason[reason] = []
            failure_by_reason[reason].append(f"{failure['strategy']}: {failure['test']}")
        
        for reason, tests in failure_by_reason.items():
            logger.info(f"   📋 {reason}:")
            for test in tests:
                logger.info(f"      • {test}")
    
    # Successful tests
    if summary['successful_tests']:
        logger.info(f"\n✅ Successful Test Cases:")
        success_by_strategy = {}
        for success in summary['successful_tests']:
            strategy = success['strategy']
            if strategy not in success_by_strategy:
                success_by_strategy[strategy] = []
            success_by_strategy[strategy].append({
                'test': success['test'],
                'methods': success['methods']
            })
        
        for strategy, tests in success_by_strategy.items():
            logger.info(f"   📋 {strategy.upper()} Strategy:")
            for test_info in tests:
                methods_str = ', '.join(test_info['methods'])
                logger.info(f"      • {test_info['test']} → [{methods_str}]")
    
    # Success rate
    if summary['total_tests_run'] > 0:
        success_rate = (len(summary['successful_tests']) / summary['total_tests_run']) * 100
        logger.info(f"\n📈 Success Rate: {success_rate:.1f}% ({len(summary['successful_tests'])}/{summary['total_tests_run']})")
    
    logger.info("=" * 60)


def _extract_method_names_from_code(code_content: str) -> List[str]:
    """Extract method names from Java code using regex."""
    if not code_content:
        return []
    
    # Regex to find method declarations in Java
    # Matches: @Test or public/private/protected + return_type + method_name + (
    method_pattern = re.compile(
        r'(?:@Test\s+)?(?:public|private|protected)\s+(?:static\s+)?(?:[\w<>\[\]]+\s+)*(\w+)\s*\(',
        re.MULTILINE
    )
    
    methods = method_pattern.findall(code_content)
    # Filter out common non-method matches like constructors or getters
    filtered_methods = [m for m in methods if not m[0].isupper()]  # Exclude constructors
    
    return filtered_methods

def _rename_methods_if_needed(code: str, original_method_name: str, strategy: str, existing_methods: set) -> str:
    """Rename methods in code if they conflict with existing methods."""
    import re
    method_names = _extract_method_names_from_code(code)
    
    for method_name in method_names:
        if method_name in existing_methods or method_name == original_method_name:
            # Add strategy suffix
            new_name = f"{method_name}_{strategy}_refactored"
            # Replace method name in code
            pattern = re.compile(rf'\bvoid\s+{re.escape(method_name)}\s*\(')
            code = pattern.sub(f'void {new_name}(', code)
            logger.info(f"    Renamed {method_name} → {new_name}")
    
    return code

def show_refactored_phase(java_project_path: Path, output_path: Path, debug_mode: bool = False) -> None:
    """Generate review-friendly Java files with refactored methods organized by strategy."""
    logger.info("\nGenerate Review-Friendly Refactored Code")
    logger.info("=" * 50)
    
    # Find refactored results file
    result_files = list(output_path.glob("*_refactored_result.csv"))
    if not result_files:
        logger.warning("No refactoring result files found. Please run refactoring phase first.")
        return
    
    # Try to match the result file with the Java project name
    java_project_name = java_project_path.name
    target_result_file = output_path / f"{java_project_name}_refactored_result.csv"
    
    if target_result_file.exists():
        results_file = target_result_file
        project_name = java_project_name
        logger.info(f"Found matching results file for project '{project_name}': {results_file}")
    else:
        # Fallback to first available file if exact match not found
        results_file = result_files[0]
        project_name = results_file.stem.replace("_refactored_result", "")
        logger.warning(f"No exact match found for project '{java_project_name}', using: {results_file}")
        logger.info(f"Available result files: {[f.name for f in result_files]}")

    df = pd.read_csv(results_file)
    df.fillna('', inplace=True)
    
    validator = CodeValidator(java_project_path)
    backup_mgr = BackupManager()
    recorder = ResultsRecorder(output_path)

    # Group by test file to process efficiently
    file_groups = df.groupby('test_path')
    
    for test_file_path_str, group_df in file_groups:
        test_file_path = Path(test_file_path_str)
        if not test_file_path.exists():
            logger.warning(f"Test file not found: {test_file_path}")
            continue
            
        logger.info(f"\nProcessing file: {test_file_path.name}")
        
        # Backup original file
        backup_mgr.backup([test_file_path])
        
        try:
            # Read original content
            original_content = test_file_path.read_text(encoding='utf-8')
            modified_content = original_content
            
            # Extract existing method names to avoid conflicts
            existing_methods = set(_extract_method_names_from_code(original_content))
            
            # Collect all imports needed for this file
            all_file_imports = []
            
            # Process each test method in this file
            method_refactorings = []  # Store refactorings for each method
            for _, row in group_df.iterrows():
                method_name = row['test_method_name']
                logger.info(f"  Processing method: {method_name}")
                
                # Collect all successful refactorings for this method
                refactorings = []
                for strategy in recorder.STRATEGY_MAPPING.keys():
                    prefix = recorder.STRATEGY_MAPPING[strategy]
                    code_col = f'{prefix}_refactored_test_case_code'
                    error_col = f'{prefix}_refactoring_error'
                    imports_col = f'{prefix}_refactored_test_case_imports'
                    
                    if code_col in row and row[code_col] and not row[error_col]:
                        imports_str = row[imports_col]
                        additional_imports = [imp.strip() for imp in imports_str.split(',') if imp.strip()] if imports_str else []
                        
                        # Rename methods if they conflict with existing ones
                        refactored_code = _rename_methods_if_needed(
                            row[code_col], method_name, strategy, existing_methods
                        )
                        
                        refactorings.append({
                            'strategy': strategy,
                            'code': refactored_code,
                            'imports': additional_imports,
                            'issue_type': row['issue_type']
                        })
                        
                        # Collect imports for this file
                        all_file_imports.extend(additional_imports)
                        
                        # Update existing methods set to track new methods
                        new_methods = _extract_method_names_from_code(refactored_code)
                        existing_methods.update(new_methods)
                
                if refactorings:
                    method_refactorings.append({
                        'method_name': method_name,
                        'refactorings': refactorings
                    })
                else:
                    logger.info(f"    No successful refactorings found for {method_name}")
            
            # Add all imports for this file using SmartImportManager (once)
            if all_file_imports:
                # CRITICAL: Analyze imports for dependency requirements BEFORE adding them
                logger.info(f"🔍 Analyzing {len(all_file_imports)} imports for dependency requirements...")
                
                # Use SmartImportManager for dependency analysis
                from .import_manager import SmartImportManager
                import_manager = SmartImportManager(java_project_path)
                third_party_deps_needed = import_manager.analyze_third_party_dependencies(all_file_imports)
                
                # Add required dependencies before proceeding
                dependency_success = True
                for dep in third_party_deps_needed:
                    logger.info(f"📚 Detected {dep['type'].upper()} usage, ensuring dependency is available...")
                    logger.debug(f"  Required imports: {', '.join(dep['imports'])}")
                    
                    if dep['type'] == 'hamcrest':
                        hamcrest_success, hamcrest_message = validator.ensure_hamcrest_dependency()
                        if hamcrest_success:
                            logger.info(f"✓ {dep['type'].upper()} dependency ready: {hamcrest_message}")
                        else:
                            logger.error(f"❌ {dep['type'].upper()} dependency failed: {hamcrest_message}")
                            dependency_success = False
                            break
                    # TODO: Add handling for other dependency types (mockito, etc.)
                    else:
                        logger.warning(f"⚠ Unknown dependency type '{dep['type']}', skipping dependency check")
                
                if dependency_success:
                    # Use SmartImportManager for intelligent import handling
                    from .import_manager import SmartImportManager
                    import_manager = SmartImportManager(java_project_path)
                    modified_content, _ = import_manager.add_missing_imports(modified_content, all_file_imports)
                else:
                    logger.error(f"❌ Dependency setup failed for file {test_file_path.name}, skipping import addition")
                    # Continue without adding imports that require missing dependencies
            
            # Now insert the refactored methods
            for method_info in method_refactorings:
                method_name = method_info['method_name']
                refactorings = method_info['refactorings']
                
                # NEW LOGIC: Insert refactored methods after the original method (similar to execution phase)
                lines = modified_content.split('\n')
                start_line, end_line = validator._find_method_span(lines, method_name)
                
                if start_line == -1 or end_line == -1:
                    logger.warning(f"    Could not find original method '{method_name}' in the file. Skipping.")
                    continue
                
                # Create comprehensive comment block for review
                header_comment = f"""
/*
 * ================================================================================
 * REFACTORED METHODS FOR: {method_name}
 * Original Issue Type: {refactorings[0]['issue_type']}
 * Generated by AAA Issue Refactor Tool
 * ================================================================================
 */"""
                
                code_blocks = [header_comment]
                
                for ref in refactorings:
                    strategy_name = ref['strategy'].upper()
                    strategy_comment = f"""
/*
 * --------------------------------------------------------------------------------
 * STRATEGY: {strategy_name} 
 * --------------------------------------------------------------------------------
 */"""
                    code_blocks.append(strategy_comment)
                    code_blocks.append(ref['code'])
                
                footer_comment = f"""
/*
 * ================================================================================
 * END OF REFACTORED METHODS FOR: {method_name}
 * ================================================================================
 */"""
                code_blocks.append(footer_comment)
                
                # Insert all blocks right after the original method (not at class end)
                full_insertion = '\n'.join(code_blocks)
                insertion_line = end_line + 1
                lines.insert(insertion_line, full_insertion)
                modified_content = '\n'.join(lines)
                
                logger.info(f"    ✓ Added {len(refactorings)} refactoring(s) for {method_name} (inserted after original method)")
            
            # Write modified content
            test_file_path.write_text(modified_content, encoding='utf-8')
            
            if debug_mode:
                logger.debug(f"\n--- Modified Content for {test_file_path} ---")
                logger.debug(modified_content[:1000] + "..." if len(modified_content) > 1000 else modified_content)
                logger.debug("=" * 60)
            
        except Exception as e:
            logger.error(f"Error processing file {test_file_path}: {e}", exc_info=debug_mode)
            backup_mgr.restore_file(test_file_path)
    
    logger.info(f"\n✓ Review-friendly code generation completed!")
    logger.info("📝 User can now review the refactored methods in the Java test files.")
    logger.info("💡 Use --keep-rf-in-project to prevent automatic restoration of original files.")
    logger.info("🔄 To restore original files, use git checkout or backup files.")


def clean_refactored_phase(java_project_path: Path, debug_mode: bool = False) -> None:
    """Clean up all refactored code from Java files using git checkout."""
    logger.info("\nClean Refactored Code")
    logger.info("=" * 50)
    
    try:
        import subprocess
        
        # Check if we're in a git repository
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=java_project_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.error(f"Java project is not a git repository: {java_project_path}")
            logger.error("Cannot clean refactored code without git. Please manually restore files.")
            return
        
        # Check git status for modified files
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", "*.java"],
            cwd=java_project_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logger.error(f"Failed to check git status: {result.stderr}")
            return
        
        modified_files = []
        for line in result.stdout.strip().split('\n'):
            if line.strip() and (line.startswith(' M') or line.startswith('M ')):
                # Extract filename from git status output
                filename = line[2:].strip()
                if filename.endswith('.java'):
                    modified_files.append(filename)
        
        if not modified_files:
            logger.info("✓ No modified Java files found. Project is already clean.")
            return
        
        logger.info(f"Found {len(modified_files)} modified Java files:")
        for file in modified_files:
            logger.info(f"  - {file}")
        
        # Use git checkout to restore all modified Java files
        logger.info("Restoring Java files to their original state...")
        result = subprocess.run(
            ["git", "checkout", "HEAD", "--"] + modified_files,
            cwd=java_project_path,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            logger.error(f"Failed to restore files: {result.stderr}")
            return
        
        logger.info(f"✓ Successfully restored {len(modified_files)} Java files to their original state.")
        
        if debug_mode:
            # Show final git status
            result = subprocess.run(
                ["git", "status", "--porcelain", "--", "*.java"],
                cwd=java_project_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            remaining_modified = [line for line in result.stdout.strip().split('\n') if line.strip()]
            if remaining_modified:
                logger.debug(f"Remaining modified files: {remaining_modified}")
            else:
                logger.debug("All Java files have been restored.")
        
    except subprocess.TimeoutExpired:
        logger.error("Git command timeout. Please manually restore Java files.")
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}", exc_info=debug_mode)
        logger.error("Please manually restore Java files using 'git checkout HEAD -- *.java'")


def pit_test_phase(java_project_path: Path, output_path: Path, rftype: str, 
                   debug_mode: bool = False, keep_files: bool = False) -> None:
    """Phase 4: PIT Mutation Testing - Evaluate refactoring quality."""
    logger.info(f"\nPhase 4: PIT Mutation Testing ({rftype.upper()} strategy)")
    logger.info("=" * 50)
    
    # Clean any existing refactored code before starting
    logger.info("Cleaning any existing refactored code before PIT testing...")
    clean_refactored_phase(java_project_path, debug_mode)
    
    logger.warning(f"PIT test phase for {rftype} strategy not yet implemented")
    # raise NotImplementedError("PIT testing phase is not yet implemented")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="aif",
        description="Refactor Java test cases to eliminate AAA pattern violations using LLMs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full refactoring pipeline
  aif --project /path/to/java/project --data /path/to/data --output /path/to/output
  
  # Discovery phase only (skip initial build if already built in IDE)
  aif --project /path/to/java/project --data /path/to/data --output /path/to/output --discovery-only --skip-initial-build

  # Refactor only (auto-discovers discovery file from output folder)
  aif --project /path/to/java/project --data /path/to/data --output /path/to/output --refactor-only --rftype aaa
  
  # Execution test only (incremental compilation always performed for quality assurance)
  aif --project /path/to/java/project --output /path/to/output --execution-test-only
  
  # Generate review-friendly code with all strategies integrated
  aif --project /path/to/java/project --output /path/to/output --show-refactored-only
  
  # Clean up refactored code after review
  aif --project /path/to/java/project --output /path/to/output --clean-refactored-only
        """
    )

    parser.add_argument(
        "--project",
        dest="java_project_path",
        required=True,
        help="Absolute path to the Java project containing test cases"
    )

    parser.add_argument(
        "--data",
        dest="data_folder_path",
        required=True,
        help="Absolute path to folder containing CSV and JSON context files"
    )

    parser.add_argument(
        "--output",
        dest="output_folder_path",
        required=True,
        help="Absolute path to folder where results will be saved"
    )

    # Refactoring strategy selection
    parser.add_argument(
        "--rftype",
        choices=["aaa", "dsl", "testsmell"],
        help="Refactoring strategy type (required for refactor-only and pit-test-only)"
    )

    # Phase flags
    phase_group = parser.add_mutually_exclusive_group()
    phase_group.add_argument(
        "--discovery-only",
        action="store_true",
        help="Run only the discovery phase (test validation)"
    )
    phase_group.add_argument(
        "--refactor-only",
        action="store_true",
        help="Run only the refactoring phase for a specified strategy"
    )
    phase_group.add_argument(
        "--execution-test-only",
        action="store_true",
        help="Run only the execution testing phase (integrate and test refactored code)"
    )
    phase_group.add_argument(
        "--pit-test-only",
        action="store_true",
        help="Run only the PIT mutation testing phase for specified strategy"
    )
    phase_group.add_argument(
        "--show-refactored-only",
        action="store_true",
        help="Generate review-friendly Java files with all refactored methods integrated by strategy blocks"
    )
    phase_group.add_argument(
        "--clean-refactored-only",
        action="store_true",
        help="Clean up all refactored code from Java files using git checkout"
    )

    # Debugging flags
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode to print LLM responses and modified file content"
    )
    parser.add_argument(
        "--keep-rf-in-project",
        dest="keep_files",
        action="store_true",
        help="Do not revert changes to Java files after test execution (useful with --debug)"
    )

    # Build management options
    parser.add_argument(
        "--skip-initial-build",
        action="store_true",
        help="Skip initial build detection if project is already built (but still perform incremental compilation)"
    )
    parser.add_argument(
        "--no-fallback-manual",
        action="store_true",
        help="Disable manual build fallback - fail immediately if automatic build fails"
    )
    parser.add_argument(
        "--build-timeout",
        type=int,
        default=600,
        help="Maximum time in seconds to wait for automatic build (default: 600)"
    )

    parser.add_argument(
        "--input-file",
        dest="input_file_path",
        help="Path to a custom input CSV file for refactor-only phase (optional, auto-discovers if not provided)"
    )

    parser.add_argument(
        "--version", "-v",
        action="version",
        version="AAA Issue Refactor v0.1.0"
    )

    # Auto-update options
    parser.add_argument(
        "--no-auto-update",
        action="store_true",
        help="Disable automatic update check and pull from GitHub"
    )
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Force update even if local changes are detected"
    )

    args = parser.parse_args()

    # Validation for phase-specific requirements
    if args.refactor_only and not args.rftype:
        parser.error("--refactor-only requires --rftype")
    
    if args.pit_test_only and not args.rftype:
        parser.error("--pit-test-only requires --rftype")

    try:
        java_path, data_path, output_path = validate_paths(
            args.java_project_path,
            args.data_folder_path,
            args.output_folder_path
        )
        
        setup_logger(output_path, args.debug)

        logger.info("AAA Issue Refactor Tool")
        logger.info("=" * 50)
        
        # Auto-update check (unless disabled)
        if not args.no_auto_update:
            try:
                check_and_auto_update(force=args.force_update)
            except Exception as e:
                logger.warning(f"Autoupdate failed: {e}")
                logger.info("Continue on the program...")

        logger.info(f"Java Project: {java_path}")
        logger.info(f"Data Folder: {data_path}")
        logger.info(f"Output Folder: {output_path}")

        # --- Phase Execution Logic ---

        discovery_output_file = None
        if args.discovery_only:
            logger.info("\nMode: Discovery Only")
            discovery_phase(java_path, data_path, output_path, args.skip_initial_build, not args.no_fallback_manual, args.build_timeout)
            
        elif args.refactor_only:
            logger.info(f"\nMode: Refactor Only ({args.rftype.upper()} strategy)")
            
            # Auto-discover or use specified input file
            if args.input_file_path:
                input_file = Path(args.input_file_path)
                logger.info(f"Using specified input file: {input_file}")
            else:
                input_file = find_discovery_file(java_path, output_path)
                if not input_file:
                    logger.error("No discovery file found. Please run discovery phase first or specify --input-file")
                    sys.exit(1)
            
            test_cases = load_test_cases_from_csv(input_file)
            refactoring_phase(test_cases, java_path, data_path, output_path, args.rftype, args.debug)
            
        elif args.execution_test_only:
            logger.info("\nMode: Execution Test Only")
            execution_test_phase(java_path, output_path, args.debug, args.keep_files, not args.no_fallback_manual, args.skip_initial_build)
            
        elif args.pit_test_only:
            logger.info(f"\nMode: PIT Test Only ({args.rftype.upper()} strategy)")
            pit_test_phase(java_path, output_path, args.rftype, args.debug, args.keep_files)
            
        elif args.show_refactored_only:
            logger.info("\nMode: Show Refactored Code for Review")
            show_refactored_phase(java_path, output_path, args.debug)
            
        elif args.clean_refactored_only:
            logger.info("\nMode: Clean Refactored Code")
            clean_refactored_phase(java_path, args.debug)
            
        else:
            # Full pipeline execution
            logger.info("\nMode: Full Pipeline")
            
            # Phase 1: Discovery
            discovery_output_file = discovery_phase(java_path, data_path, output_path, args.skip_initial_build, not args.no_fallback_manual, args.build_timeout)
            test_cases = load_test_cases_from_csv(discovery_output_file)
            
            # Phase 2: Refactoring (for each specified strategy, or default to 'aaa')
            strategies_to_run = [args.rftype] if args.rftype else ['aaa', 'dsl', 'testsmell']
            logger.info(f"Will run refactoring for strategies: {', '.join(strategies_to_run)}")
            
            for strategy in strategies_to_run:
                if strategy not in ResultsRecorder.STRATEGY_MAPPING:
                    logger.warning(f"Unknown strategy '{strategy}', skipping.")
                    continue
                refactoring_phase(test_cases, java_path, data_path, output_path, strategy, args.debug)
            
            # Phase 3: Execution Testing
            execution_test_phase(java_path, output_path, args.debug, args.keep_files, not args.no_fallback_manual, args.skip_initial_build)
            
            # Phase 4: PIT Testing
            for strategy in strategies_to_run:
                if strategy not in ResultsRecorder.STRATEGY_MAPPING:
                    continue
                pit_test_phase(java_path, output_path, strategy, args.debug, args.keep_files)

        logger.info("\n✓ Pipeline completed successfully.")

    except KeyboardInterrupt:
        logger.warning("\n⚠ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"\n✗ An unexpected error occurred: {str(e)}", exc_info=args.debug)
        sys.exit(1)


if __name__ == "__main__":
    main() 