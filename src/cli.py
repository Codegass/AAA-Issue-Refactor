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


def discovery_phase(java_project_path: Path, data_folder_path: Path, output_path: Path) -> Path:
    """Phase 1: Test Discovery & Validation."""
    logger.info("Phase 1: Test Discovery & Validation")
    logger.info("=" * 50)

    discovery = TestDiscovery(java_project_path, data_folder_path)
    logger.info("Loading AAA results from CSV...")
    test_cases = discovery.load_aaa_results()
    logger.info(f"Found {len(test_cases)} initial test cases")

    logger.info("Validating test cases...")
    validated_cases = discovery.validate_test_cases(test_cases)
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
        test_case = TestCase(
            project_name=row['project_name'],
            test_class_name=row['test_class_name'],
            test_method_name=row['test_method_name'],
            issue_type=row['issue_type']
        )
        test_case.test_path = row.get('test_path', 'not found')
        test_case.test_case_loc = row.get('test_case_LOC', 0)
        test_case.runable = row.get('runable', 'no')
        test_case.pass_status = row.get('pass', 'no')
        test_cases.append(test_case)
    return test_cases


def refactoring_phase(test_cases: List[TestCase], java_project_path: Path,
                     data_folder_path: Path, output_path: Path, rftype: str,
                      debug_mode: bool = False) -> None:
    """Phase 2: Test Refactoring. Generates code but does not execute it."""
    logger.info(f"\nPhase 2: Test Refactoring ({rftype.upper()} strategy)")
    logger.info("=" * 50)

    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    refactor = TestRefactor(prompts_dir, data_folder_path, rftype, output_path)
    recorder = ResultsRecorder(output_path)

    runnable_cases = [tc for tc in test_cases if tc.runable == "yes"]
    cases_to_refactor = [tc for tc in runnable_cases if tc.issue_type.lower().strip() != 'good aaa']
    logger.info(f"Processing {len(runnable_cases)} runnable test cases ({len(cases_to_refactor)} need refactoring)...")

    results = []
    project_name = ""
    if runnable_cases:
        project_name = runnable_cases[0].project_name

        for i, test_case in enumerate(runnable_cases, 1):
            logger.info(f"\n[{i}/{len(runnable_cases)}] Processing: {test_case.test_class_name}.{test_case.test_method_name}")
            logger.info(f"Issue Type: {test_case.issue_type}")

            original_code = ""
            original_imports = []
            try:
                context = refactor.load_test_context(
                    test_case.project_name, test_case.test_class_name, test_case.test_method_name
                )
                original_code = context.test_case_source_code
                original_imports = context.imported_packages

                if test_case.issue_type.lower().strip() == 'good aaa':
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
                         debug_mode: bool = False, keep_files: bool = False) -> None:
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
    
    project_name = result_files[0].stem.replace("_refactored_result", "")
    results_file = result_files[0]
    logger.info(f"Found results file for project '{project_name}': {results_file}")

    df = pd.read_csv(results_file)
    df.fillna('', inplace=True)
    
    validator = CodeValidator(java_project_path)
    recorder = ResultsRecorder(output_path)
    backup_mgr = BackupManager()

    # Get a unique list of all test files to back them up once
    all_test_paths = {p for p in df['test_path'].unique() if p and Path(p).exists()}
    backup_mgr.backup([Path(p) for p in all_test_paths])

    try:
        for strategy in recorder.STRATEGY_MAPPING.keys():
            prefix = recorder.STRATEGY_MAPPING[strategy]
            code_col = f'{prefix}_refactored_test_case_code'
            error_col = f'{prefix}_refactoring_error'
            result_col = f'{prefix}_refactored_test_case_result'
            
            if code_col not in df.columns:
                continue

            logger.info(f"\n--- Testing Strategy: {strategy.upper()} ---")
            
            # Filter for rows that have successful refactorings for this strategy
            strategy_df = df[(df[code_col] != '') & (df[error_col] == '')].copy()
            if strategy_df.empty:
                logger.info("No successful refactorings to test for this strategy.")
                continue

            for _, row in strategy_df.iterrows():
                test_path = Path(row['test_path'])
                logger.info(f"Testing {row['test_class_name']}.{row['test_method_name']}...")
                
                # We need to re-integrate code for each test, as previous integrations are reverted
                # This is inefficient but safe. A better way would be to group by file.
                # For now, we restore, modify, test, and move to the next.
                backup_mgr.restore_file(test_path)
                
                # Integrate the code
                is_one_to_many = row['issue_type'].lower().strip() == "multiple aaa"
                # Parse additional imports, filtering out empty strings
                imports_str = row[f'{prefix}_refactored_test_case_imports']
                additional_imports = [imp.strip() for imp in imports_str.split(',') if imp.strip()] if imports_str else []
                success, modified_content, _ = validator.integrate_refactored_method(
                    test_path, row['test_method_name'], row[code_col], strategy,
                    additional_imports, is_one_to_many,
                    debug_mode=debug_mode
                )
                
                if not success:
                    logger.warning(f"  ✗ Code integration failed for {row['test_method_name']}.")
                    df.loc[df.index == row.name, result_col] = "integration_failed"
                    continue

                test_path.write_text(modified_content, encoding='utf-8')
                
                # Discover test methods to run from the result CSV
                method_names_col = f'{prefix}_refactored_method_names'
                if method_names_col in row and row[method_names_col]:
                    refactored_methods = row[method_names_col].split(',')
                else:
                    refactored_methods = []

                if not refactored_methods:
                    logger.warning(f"  Could not find any refactored method names in result file.")
                    df.loc[df.index == row.name, result_col] = "no_test_found"
                    continue

                logger.info(f"  Running refactored test(s): {', '.join(refactored_methods)}")
                all_passed = True
                for method in refactored_methods:
                    passed, output = validator.run_specific_test(row['test_class_name'], method, test_path)
                    if not passed:
                        all_passed = False
                        logger.warning(f"  - Method '{method}' FAILED.")
                        if debug_mode: logger.debug(f"Test output:\n{output}")
                        break
                
                test_result = "pass" if all_passed else "fail"
                logger.info(f"  ✓ Test result: {test_result.upper()}")
                df.loc[df.index == row.name, result_col] = test_result
        
        # After all strategies are tested, save the final, updated dataframe
        df.to_csv(results_file, index=False, quoting=csv.QUOTE_ALL)
        logger.info(f"\n✓ Execution results saved to {results_file}")

    finally:
        if not keep_files:
            logger.info("Restoring all original files...")
            backup_mgr.restore_all()
        backup_mgr.cleanup()


def _extract_method_names_from_code(code: str) -> List[str]:
    """Extract all test method names from Java code."""
    import re
    # Find all @Test annotated methods
    pattern = re.compile(r'@Test\s+[^}]*?void\s+([a-zA-Z_]\w*)\s*\(', re.MULTILINE | re.DOTALL)
    return pattern.findall(code)

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
    
    project_name = result_files[0].stem.replace("_refactored_result", "")
    results_file = result_files[0]
    logger.info(f"Found results file for project '{project_name}': {results_file}")

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
            
            # Process each test method in this file
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
                        
                        # Update existing methods set to track new methods
                        new_methods = _extract_method_names_from_code(refactored_code)
                        existing_methods.update(new_methods)
                
                if not refactorings:
                    logger.info(f"    No successful refactorings found for {method_name}")
                    continue
                
                # Add imports for all refactorings
                all_imports = []
                for ref in refactorings:
                    all_imports.extend(ref['imports'])
                
                if all_imports:
                    modified_content, _ = validator._add_imports(modified_content, all_imports)
                
                # Add refactored methods grouped by strategy (DO NOT comment out original)
                lines = modified_content.split('\n')
                insertion_line = validator._find_class_closing_brace(lines)
                
                if insertion_line == -1:
                    logger.error(f"    Could not find class closing brace")
                    continue
                
                # Create comprehensive comment block
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
                
                # Insert all blocks
                full_insertion = '\n'.join(code_blocks)
                lines.insert(insertion_line, full_insertion)
                modified_content = '\n'.join(lines)
                
                logger.info(f"    ✓ Added {len(refactorings)} refactoring(s) for {method_name}")
            
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
    logger.info("📝 Students can now review the refactored methods in the Java test files.")
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
  
  # Discovery phase only
  aif --project /path/to/java/project --data /path/to/data --output /path/to/output --discovery-only

  # Refactor only (auto-discovers discovery file from output folder)
  aif --project /path/to/java/project --data /path/to/data --output /path/to/output --refactor-only --rftype aaa
  
  # Refactor only with custom input file
  aif --project /path/to/java/project --data /path/to/data --output /path/to/output --refactor-only --rftype aaa --input-file /path/to/custom.csv
  
  # Generate review-friendly code with all strategies integrated
  aif --project /path/to/java/project --data /path/to/data --output /path/to/output --show-refactored-only
  
  # Clean up refactored code after review
  aif --project /path/to/java/project --data /path/to/data --output /path/to/output --clean-refactored-only
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
            discovery_phase(java_path, data_path, output_path)
            
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
            execution_test_phase(java_path, output_path, args.debug, args.keep_files)
            
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
            discovery_output_file = discovery_phase(java_path, data_path, output_path)
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
            execution_test_phase(java_path, output_path, args.debug, args.keep_files)
            
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