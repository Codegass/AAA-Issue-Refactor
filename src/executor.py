"""Test execution and results recording."""

import csv
import time
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import asdict

from .discovery import TestCase
from .refactor import RefactoringResult

class ResultsRecorder:
    """Records refactoring results to a wide-table CSV format supporting multiple strategies."""

    STRATEGY_MAPPING = {
        'aaa': 'v1_aaa',
        'dsl': 'v2_dsl', 
        'testsmell': 'v3_testsmell'
    }
    
    def __init__(self, output_path: Path):
        self.output_path = output_path

    def get_common_columns(self) -> List[str]:
        """Get the common columns used across all strategies."""
        return [
            'project_name', 'test_class_name', 'test_method_name', 'test_path', 'issue_type',
            'original_test_case_code', 'original_test_case_LOC', 'original_test_case_result',
            'original_test_case_imports'
        ]

    def get_strategy_columns(self, strategy: str) -> List[str]:
        """Get the strategy-specific columns."""
        prefix = self.STRATEGY_MAPPING.get(strategy, strategy)
        return [
            f'{prefix}_refactored_test_case_code',
            f'{prefix}_refactored_test_case_LOC', 
            f'{prefix}_refactored_test_case_result',
            f'{prefix}_refactored_test_case_imports',
            f'{prefix}_refactored_method_names',
            f'{prefix}_refactoring_loop',
            f'{prefix}_token_usage',
            f'{prefix}_refactoring_cost',
            f'{prefix}_refactoring_time',
            f'{prefix}_refactoring_error',
            f'{prefix}_refactoring_chat_history'
        ]

    def get_all_columns(self) -> List[str]:
        """Get all possible columns for the wide table."""
        columns = self.get_common_columns()
        for strategy in self.STRATEGY_MAPPING.keys():
            columns.extend(self.get_strategy_columns(strategy))
        return columns

    def save_results(self, project_name: str, strategy: str, results: List[Dict[str, Any]]) -> Path:
        """Saves/updates results for a specific strategy into the wide-table CSV."""
        output_file = self.output_path / f"{project_name}_refactored_result.csv"
        
        try:
            if output_file.exists() and output_file.stat().st_size > 0:
                df = pd.read_csv(output_file)
            else:
                df = pd.DataFrame(columns=self.get_all_columns())
        except pd.errors.EmptyDataError:
            df = pd.DataFrame(columns=self.get_all_columns())
        
        # Ensure all columns from the master list are present
        for col in self.get_all_columns():
            if col not in df.columns:
                df[col] = None
        
        # Use a more robust way to merge data
        updates_df = pd.DataFrame(results)
        
        # Define keys for merging
        merge_keys = ['project_name', 'test_class_name', 'test_method_name']
        
        # Separate common and strategy-specific columns for the update
        common_cols = self.get_common_columns()
        strategy_cols = self.get_strategy_columns(strategy)
        
        # If the original dataframe is not empty, merge. Otherwise, the new data is the dataframe.
        if not df.empty:
            # Set index for easy update
            df.set_index(merge_keys, inplace=True)
            updates_df.set_index(merge_keys, inplace=True)

            # Update common columns from the new data if they are not already set
            common_to_update = [col for col in common_cols if col not in merge_keys]
            df.update(updates_df[common_to_update], overwrite=False) # Fills NaNs
            
            # Always overwrite strategy-specific columns for the current run
            df.update(updates_df[strategy_cols], overwrite=True)
            
            # Add new rows for test cases not previously seen
            new_rows = updates_df[~updates_df.index.isin(df.index)]
            df = pd.concat([df, new_rows])
            
            df.reset_index(inplace=True)
        else:
            df = updates_df

        # Reorder columns to the canonical order and save
        df = df.reindex(columns=self.get_all_columns())
        df.to_csv(output_file, index=False, quoting=csv.QUOTE_ALL)
        return output_file

    def create_result_record(self, test_case: TestCase, original_code: str, original_imports: List[str],
                                    refactoring_result: RefactoringResult, strategy: str) -> Dict[str, Any]:
        """Creates a result record dictionary for a specific strategy."""
        prefix = self.STRATEGY_MAPPING.get(strategy, strategy)
        
        record = {
            'project_name': test_case.project_name,
            'test_class_name': test_case.test_class_name,
            'test_method_name': test_case.test_method_name,
            'test_path': test_case.test_path,
            'issue_type': test_case.issue_type,
            'original_test_case_code': original_code,
            'original_test_case_LOC': len((original_code or "").split('\n')),
            'original_test_case_result': test_case.pass_status,
            'original_test_case_imports': ", ".join(original_imports),
        }
        
        record.update({
            f'{prefix}_refactored_test_case_code': refactoring_result.refactored_code or "",
            f'{prefix}_refactored_test_case_LOC': len((refactoring_result.refactored_code or "").split('\n')),
            f'{prefix}_refactored_test_case_result': "not_run",  # Default status
            f'{prefix}_refactored_test_case_imports': ", ".join(refactoring_result.additional_imports) if refactoring_result.additional_imports else "",
            f'{prefix}_refactored_method_names': ",".join(refactoring_result.refactored_method_names) if refactoring_result.refactored_method_names else "",
            f'{prefix}_refactoring_loop': refactoring_result.iterations,
            f'{prefix}_token_usage': refactoring_result.tokens_used,
            f'{prefix}_refactoring_cost': refactoring_result.cost,
            f'{prefix}_refactoring_time': refactoring_result.processing_time,
            f'{prefix}_refactoring_error': refactoring_result.error_message or "",
            f'{prefix}_refactoring_chat_history': refactoring_result.chat_history or ""
        })
        
        return record