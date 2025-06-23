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
    refactor = TestRefactor(prompts_dir, data_folder_path, rftype)
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
                refactoring_result = refactor.refactor_test_case(test_case, debug_mode=debug_mode)
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


def execution_test_phase(java_project_path: Path, output_path: Path, 
                         debug_mode: bool = False, keep_files: bool = False) -> None:
    """Phase 3: Execution Testing. Integrates and tests all refactored code."""
    logger.info("\nPhase 3: Execution Testing")
    logger.info("=" * 50)
    
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
                success, modified_content, _ = validator.integrate_refactored_method(
                    test_path, row['test_method_name'], row[code_col], strategy,
                    row[f'{prefix}_refactored_test_case_imports'].split(','), is_one_to_many,
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
                    passed, output = validator.run_specific_test(row['test_class_name'], method)
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


def pit_test_phase(java_project_path: Path, output_path: Path, rftype: str, 
                   debug_mode: bool = False, keep_files: bool = False) -> None:
    """Phase 4: PIT Mutation Testing - Evaluate refactoring quality."""
    logger.info(f"\nPhase 4: PIT Mutation Testing ({rftype.upper()} strategy)")
    logger.info("=" * 50)
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

  # Refactor only, using results from a previous discovery run
  aif --project /path/to/java/project --data /path/to/data --output /path/to/output --refactor-only --input-file /path/to/output/project_AAA_Refactor_Cases.csv
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
        help="Path to a custom input CSV file for a phase (e.g., discovery results)"
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
    
    if args.refactor_only and not args.input_file_path:
        parser.error("--refactor-only requires --input-file (e.g., from a discovery run)")

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
                logger.warning(f"自动更新检查失败: {e}")
                logger.info("继续执行程序...")

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
            if not args.input_file_path:
                parser.error("--refactor-only requires --input-file (e.g., from a discovery run)")
            input_file = Path(args.input_file_path)
            test_cases = load_test_cases_from_csv(input_file)
            refactoring_phase(test_cases, java_path, data_path, output_path, args.rftype, args.debug)
            
        elif args.execution_test_only:
            logger.info("\nMode: Execution Test Only")
            execution_test_phase(java_path, output_path, args.debug, args.keep_files)
            
        elif args.pit_test_only:
            logger.info(f"\nMode: PIT Test Only ({args.rftype.upper()} strategy)")
            pit_test_phase(java_path, output_path, args.rftype, args.debug, args.keep_files)
            
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