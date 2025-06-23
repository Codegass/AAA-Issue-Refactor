"""Usage tracking for LLM refactoring operations."""

import csv
import time
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger('aif')

@dataclass
class UsageRecord:
    """Record for tracking usage statistics per test case."""
    project: str
    test_class: str
    test_case: str
    cost: float
    time: float
    refactoring_loop: int
    strategy: str = ""
    tokens_used: int = 0
    success: bool = False
    error_message: str = ""

class UsageTracker:
    """Tracks and records LLM usage statistics."""
    
    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.records: List[UsageRecord] = []
    
    def start_timing(self) -> float:
        """Start timing for a refactoring operation."""
        return time.time()
    
    def record_usage(self, project: str, test_class: str, test_case: str, 
                    cost: float, start_time: float, refactoring_loops: int,
                    strategy: str = "", tokens_used: int = 0, 
                    success: bool = False, error_message: str = "") -> None:
        """Record usage statistics for a test case refactoring."""
        end_time = time.time()
        processing_time = end_time - start_time
        
        record = UsageRecord(
            project=project,
            test_class=test_class,
            test_case=test_case,
            cost=cost,
            time=processing_time,
            refactoring_loop=refactoring_loops,
            strategy=strategy,
            tokens_used=tokens_used,
            success=success,
            error_message=error_message
        )
        
        self.records.append(record)
        logger.debug(f"Usage recorded: {test_class}.{test_case} - ${cost:.4f}, {processing_time:.2f}s, {refactoring_loops} loops")
    
    def save_usage_statistics(self, project_name: str) -> Path:
        """Save all usage records to a CSV file."""
        if not self.records:
            logger.warning("No usage records to save")
            return None
            
        output_file = self.output_path / f"{project_name}-usage.csv"
        
        fieldnames = [
            'project', 'testclass', 'testcase', 'strategy', 'cost', 'time', 
            'refactoring_loop', 'tokens_used', 'success', 'error_message'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for record in self.records:
                writer.writerow({
                    'project': record.project,
                    'testclass': record.test_class,
                    'testcase': record.test_case,
                    'strategy': record.strategy,
                    'cost': f"{record.cost:.6f}",  # 6 decimal places for precision
                    'time': f"{record.time:.3f}",   # 3 decimal places for seconds
                    'refactoring_loop': record.refactoring_loop,
                    'tokens_used': record.tokens_used,
                    'success': record.success,
                    'error_message': record.error_message
                })
        
        # Log summary statistics
        total_cost = sum(r.cost for r in self.records)
        total_time = sum(r.time for r in self.records)
        total_loops = sum(r.refactoring_loop for r in self.records)
        successful_cases = sum(1 for r in self.records if r.success)
        
        logger.info(f"Usage statistics saved to {output_file}")
        logger.info(f"Summary: {len(self.records)} cases, ${total_cost:.4f} total cost, "
                   f"{total_time:.2f}s total time, {total_loops} total loops, "
                   f"{successful_cases}/{len(self.records)} successful")
        
        return output_file
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics for all recorded usage."""
        if not self.records:
            return {}
            
        return {
            'total_cases': len(self.records),
            'successful_cases': sum(1 for r in self.records if r.success),
            'total_cost': sum(r.cost for r in self.records),
            'total_time': sum(r.time for r in self.records),
            'total_loops': sum(r.refactoring_loop for r in self.records),
            'total_tokens': sum(r.tokens_used for r in self.records),
            'average_cost_per_case': sum(r.cost for r in self.records) / len(self.records),
            'average_time_per_case': sum(r.time for r in self.records) / len(self.records),
            'average_loops_per_case': sum(r.refactoring_loop for r in self.records) / len(self.records),
        } 