"""Test execution and results recording."""

import csv
import time
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import asdict

from .discovery import TestCase
from .refactor import RefactoringResult

class ResultsRecorder:
    """Records refactoring results to CSV."""
    
    def __init__(self, output_path: Path):
        self.output_path = output_path
    
    def save_results(self, project_name: str, results: List[Dict[str, Any]]) -> None:
        """Save refactoring results to CSV file."""
        output_file = self.output_path / f"{project_name}_refactored_result.csv"
        
        fieldnames = [
            'project_name', 'test_class_name', 'test_method_name', 'test_path', 'issue_type',
            'original_test_case_code', 'original_test_case_LOC', 'original_test_case_result',
            'refactored_test_case_code', 'refactored_test_case_LOC', 'refactored_test_case_result',
            'refactoring_loop', 'token_usage', 'refactoring_cost', 'refactoring_time',
            'refactoring_error', 'refactoring_chat_history'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
    
    def create_result_record(self, test_case: TestCase, original_code: str, refactoring_result: RefactoringResult,
                           original_test_result: str = "unknown", refactored_test_result: str = "unknown") -> Dict[str, Any]:
        """Create a result record for a test case."""
        return {
            'project_name': test_case.project_name,
            'test_class_name': test_case.test_class_name,
            'test_method_name': test_case.test_method_name,
            'test_path': test_case.test_path,
            'issue_type': test_case.issue_type,
            'original_test_case_code': original_code,
            'original_test_case_LOC': test_case.test_case_loc,
            'original_test_case_result': original_test_result,
            'refactored_test_case_code': refactoring_result.refactored_code or "",
            'refactored_test_case_LOC': len((refactoring_result.refactored_code or "").split('\n')),
            'refactored_test_case_result': refactored_test_result,
            'refactoring_loop': refactoring_result.iterations,
            'token_usage': refactoring_result.tokens_used,
            'refactoring_cost': refactoring_result.cost,
            'refactoring_time': refactoring_result.processing_time,
            'refactoring_error': refactoring_result.error_message or "",
            'refactoring_chat_history': refactoring_result.chat_history or ""
        }