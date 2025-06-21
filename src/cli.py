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

from .discovery import TestDiscovery, TestCase
from .refactor import TestRefactor, RefactoringResult
from .validator import CodeValidator
from .executor import ResultsRecorder


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


def discovery_phase(java_project_path: Path, data_folder_path: Path, output_path: Path) -> List[TestCase]:
    """Phase 1: Test Discovery & Validation."""
    print("Phase 1: Test Discovery & Validation")
    print("=" * 50)

    discovery = TestDiscovery(java_project_path, data_folder_path)

    # Load test cases from CSV
    print("Loading AAA results from CSV...")
    test_cases = discovery.load_aaa_results()
    print(f"Found {len(test_cases)} test cases")

    # Validate test cases
    print("Validating test cases...")
    validated_cases = discovery.validate_test_cases(test_cases)

    # Count statistics
    runnable_count = sum(1 for tc in validated_cases if tc.runable == "yes")
    print(f"Runnable test cases: {runnable_count}/{len(validated_cases)}")

    # Save results
    print("Saving refactor cases CSV...")
    output_file = discovery.save_refactor_cases_csv(validated_cases, output_path)
    print(f"✓ Discovery results saved to {output_file}")

    return validated_cases


def load_test_cases_from_csv(input_file: Path) -> List[TestCase]:
    """Load test cases from a specified CSV file."""
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    df = pd.read_csv(input_file)
    test_cases = []
    for _, row in df.iterrows():
        test_case = TestCase(
            project_name=row['project_name'],
            test_class_name=row['test_class_name'],
            test_method_name=row['test_method_name'],
            issue_type=row['issue_type']
        )
        test_case.test_path = row.get('test_path')
        test_case.test_case_loc = row.get('test_case_LOC')
        test_case.runable = row.get('runable', 'no')
        test_case.pass_status = row.get('pass', 'no')
        test_cases.append(test_case)
    return test_cases


def refactoring_phase(test_cases: List[TestCase], java_project_path: Path,
                     data_folder_path: Path, output_path: Path, 
                     debug_mode: bool = False, keep_files: bool = False) -> None:
    """Phase 2: Test Refactoring Loop."""
    print("\nPhase 2: Test Refactoring Loop")
    print("=" * 50)

    # Initialize components
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    refactor = TestRefactor(prompts_dir, data_folder_path)
    validator = CodeValidator(java_project_path)
    recorder = ResultsRecorder(output_path)

    # Filter to runnable test cases only
    runnable_cases = [tc for tc in test_cases if tc.runable == "yes"]
    
    cases_to_refactor = [tc for tc in runnable_cases if tc.issue_type.lower().strip() != 'good aaa']
    print(f"Processing {len(runnable_cases)} runnable test cases ({len(cases_to_refactor)} need refactoring)...")

    results = []

    for i, test_case in enumerate(runnable_cases, 1):
        print(f"\n[{i}/{len(runnable_cases)}] Processing: {test_case.test_class_name}.{test_case.test_method_name}")
        print(f"Issue Type: {test_case.issue_type}")

        # --- Debug and Cleanup Setup ---
        original_content: Optional[str] = None
        test_file_path = Path(test_case.test_path) if test_case.test_path and test_case.test_path != "not found" else None

        try:
            # Read original content if file exists, for potential restoration
            if test_file_path and test_file_path.exists():
                original_content = test_file_path.read_text(encoding='utf-8')

            # This inner try/except handles errors for a single test case
            try:
                if test_case.issue_type.lower().strip() == 'good aaa':
                    print("  ✓ Skipping: No refactoring needed.")
                    # Create a "skipped" result record for the report
                    try:
                        context = refactor.load_test_context(
                            test_case.project_name, 
                            test_case.test_class_name, 
                            test_case.test_method_name
                        )
                        original_code = context.test_case_source_code
                        
                        skipped_result = RefactoringResult(success=True, refactored_code=original_code, error_message="Skipped: Good AAA")
                        result_record = recorder.create_result_record(
                            test_case, 
                            original_code, 
                            skipped_result,
                            original_test_result=test_case.pass_status,
                            refactored_test_result="skipped"
                        )
                        results.append(result_record)
                    except Exception as e:
                        print(f"  ✗ Error creating skipped record: {str(e)}")
                        # Handle error record creation
                    continue

                # Load original test context for code extraction
                context = refactor.load_test_context(
                    test_case.project_name, 
                    test_case.test_class_name, 
                    test_case.test_method_name
                )
                original_code = context.test_case_source_code
                
                # Perform refactoring
                print("  Refactoring...")
                refactoring_result = refactor.refactor_test_case(test_case)
                
                if debug_mode:
                    print("\n--- LLM Debug Info ---")
                    print(f"Reasoning:\n{refactoring_result.reasoning}")
                    print(f"Refactored Code:\n---\n{refactoring_result.refactored_code}\n---")
                    print("----------------------\n")

                if refactoring_result.success:
                    print(f"  ✓ Refactoring successful ({refactoring_result.iterations} iterations)")

                    # Integrate refactored code
                    if test_file_path and test_file_path != "not found":
                        test_file_path = Path(test_case.test_path)
                        integration_success = validator.integrate_refactored_method(
                            test_file_path,
                            test_case.test_method_name,
                            refactoring_result.refactored_code
                        )

                        if integration_success:
                            print("  ✓ Code integration successful")

                            # Run refactored test
                            print("  Running refactored test...")
                            refactored_method_name = f"{test_case.test_method_name}_refactored"
                            test_success, test_output = validator.run_specific_test(
                                test_case.test_class_name,
                                refactored_method_name
                            )

                            refactored_test_result = "pass" if test_success else "fail"
                            print(f"  Test result: {refactored_test_result}")

                        else:
                            print("  ✗ Code integration failed")
                            refactored_test_result = "integration_failed"
                    else:
                        print("  ⚠ No test file found for integration")
                        refactored_test_result = "no_file"

                else:
                    print(f"  ✗ Refactoring failed: {refactoring_result.error_message}")
                    refactored_test_result = "refactoring_failed"

                # Create result record
                result_record = recorder.create_result_record(
                    test_case,
                    original_code,
                    refactoring_result,
                    original_test_result="unknown",  # Could be determined by running original test
                    refactored_test_result=refactored_test_result
                )
                results.append(result_record)

                if integration_success and debug_mode:
                    print(f"  Debug: File '{test_file_path}' has been modified for testing.")

            except Exception as e:
                print(f"  ✗ Error processing test case: {str(e)}")
                # Create error result record
                error_result = RefactoringResult(success=False, error_message=str(e))
                result_record = recorder.create_result_record(
                    test_case, 
                    getattr(context, 'test_case_source_code', ''), 
                    error_result,
                    refactored_test_result="error"
                )
                results.append(result_record)

        finally:
            # --- Auto-cleanup Logic ---
            if original_content is not None and not keep_files:
                test_file_path.write_text(original_content, encoding='utf-8')
                if debug_mode:
                    print(f"  Debug: Reverted changes in '{test_file_path}'.")

    # Save all results
    print(f"\nSaving results for {len(results)} test cases...")
    if results:
        recorder.save_results(runnable_cases[0].project_name, results)
        print("✓ Results saved successfully")


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

    # Mode flags
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--discovery-only",
        action="store_true",
        help="Run only the discovery phase (test validation)"
    )
    mode_group.add_argument(
        "--refactor-only",
        action="store_true",
        help="Run only the refactoring phase, requires --input-file"
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
        help="Path to the input CSV file for refactoring (required with --refactor-only)"
    )

    parser.add_argument(
        "--version", "-v",
        action="version",
        version="AAA Issue Refactor v0.1.0"
    )

    args = parser.parse_args()

    if args.refactor_only and not args.input_file_path:
        parser.error("--refactor-only requires --input-file")

    try:
        # Validate paths
        java_path, data_path, output_path = validate_paths(
            args.java_project_path,
            args.data_folder_path,
            args.output_folder_path
        )

        print("AAA Issue Refactor Tool")
        print("=" * 50)
        print(f"Java Project: {java_path}")
        print(f"Data Folder: {data_path}")
        print(f"Output Folder: {output_path}")
        print()

        test_cases = []
        if args.refactor_only:
            # Phase 2 only: Load from specified file
            print("Mode: Refactor Only")
            print("=" * 50)
            input_file = Path(args.input_file_path).resolve()
            test_cases = load_test_cases_from_csv(input_file)
            print(f"Loaded {len(test_cases)} test cases from {input_file}")

        else:
            # Phase 1: Discovery (runs by default or with --discovery-only)
            test_cases = discovery_phase(java_path, data_path, output_path)

        if args.discovery_only:
            print("\n✓ Discovery phase completed successfully")
            return

        # Phase 2: Refactoring
        refactoring_phase(test_cases, java_path, data_path, output_path, args.debug, args.keep_files)

        print("\n✓ Refactoring pipeline completed successfully")

    except KeyboardInterrupt:
        print("\n⚠ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main() 