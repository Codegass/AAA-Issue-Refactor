#!/usr/bin/env python3
"""
PIT Mutation Testing Module

This module handles PIT (Pitest) mutation testing for evaluating the quality
of refactored test cases compared to original test cases.
"""

import logging
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import subprocess
import json
import time

from .build_system import create_build_system, BuildSystem
from .utils import CommandExecutor, BackupManager

logger = logging.getLogger('aif')


@dataclass
class PITResult:
    """Result of PIT mutation testing."""
    test_class: str
    test_method: str
    mutation_score: float  # Percentage of mutants killed
    line_coverage: float   # Line coverage percentage
    mutants_killed: int
    mutants_survived: int
    total_mutants: int
    execution_time: float
    pit_output: str
    success: bool
    error_message: Optional[str] = None
    
    def __str__(self) -> str:
        return (f"PIT Results for {self.test_class}.{self.test_method}:\n"
                f"  Mutation Score: {self.mutation_score:.1%}\n"
                f"  Line Coverage: {self.line_coverage:.1%}\n"
                f"  Mutants: {self.mutants_killed} killed, {self.mutants_survived} survived, {self.total_mutants} total\n"
                f"  Execution Time: {self.execution_time:.2f}s\n"
                f"  Success: {self.success}")


@dataclass
class PITComparison:
    """Comparison between original and refactored test PIT results."""
    original: PITResult
    refactored: PITResult
    
    @property
    def mutation_score_improvement(self) -> float:
        """Calculate improvement in mutation score."""
        return self.refactored.mutation_score - self.original.mutation_score
    
    @property
    def coverage_improvement(self) -> float:
        """Calculate improvement in line coverage."""
        return self.refactored.line_coverage - self.original.line_coverage
    
    @property
    def quality_improvement(self) -> str:
        """Assess overall quality improvement."""
        if not self.original.success or not self.refactored.success:
            return "error"
        
        mutation_improvement = self.mutation_score_improvement
        if mutation_improvement > 0.05:  # 5% threshold
            return "improved"
        elif mutation_improvement < -0.05:
            return "degraded"
        else:
            return "unchanged"
    
    def __str__(self) -> str:
        return (f"PIT Comparison:\n"
                f"  Mutation Score: {self.original.mutation_score:.1%} → {self.refactored.mutation_score:.1%} "
                f"({self.mutation_score_improvement:+.1%})\n"
                f"  Line Coverage: {self.original.line_coverage:.1%} → {self.refactored.line_coverage:.1%} "
                f"({self.coverage_improvement:+.1%})")


class PITTester:
    """Handles PIT mutation testing for refactored test cases."""
    
    def __init__(self, java_project_path: Path, output_path: Path):
        """
        Initialize PIT tester.
        
        Args:
            java_project_path: Path to the Java project
            output_path: Path for output files
        """
        self.java_project_path = java_project_path
        self.output_path = output_path
        self.executor = CommandExecutor(java_project_path)
        self.backup_manager = BackupManager()
        
        # Use the new build system abstraction
        self.build_system = create_build_system(java_project_path)
        logger.info(f"Detected build system: {self.build_system.get_build_system_name()}")
    
    def run_pit_baseline(self, test_class: str, test_method: str) -> PITResult:
        """
        Run PIT mutation testing on the original test method.
        
        Args:
            test_class: Fully qualified test class name
            test_method: Test method name
            
        Returns:
            PITResult with baseline metrics
        """
        logger.info(f"Running baseline PIT for {test_class}.{test_method}")
        
        start_time = time.time()
        
        try:
            # Construct PIT command based on build system
            build_system_name = self.build_system.get_build_system_name().lower()
            if "maven" in build_system_name:
                command = [
                    "mvn", "org.pitest:pitest-maven:mutationCoverage",
                    f"-DtargetClasses={test_class.replace('.', '/')}*",
                    f"-DtargetTests={test_class}.{test_method}",
                    "-DoutputFormats=XML,HTML",
                    "-DwithHistory=false"
                ]
            elif "gradle" in build_system_name:
                command = [
                    "./gradlew", "pitest",
                    f"-PtargetClasses={test_class.replace('.', '/')}*",
                    f"-PtargetTests={test_class}.{test_method}"
                ]
            else:
                raise ValueError(f"Unsupported build system for PIT: {build_system_name}")
            
            # Execute PIT command
            success, output, error_output = self.executor.run_command(
                command, timeout=600  # 10 minutes timeout
            )
            
            execution_time = time.time() - start_time
            
            if success:
                # Parse PIT results
                pit_result = self._parse_pit_results(test_class, test_method, output)
                pit_result.execution_time = execution_time
                pit_result.pit_output = output
                pit_result.success = True
                
                logger.info(f"Baseline PIT completed: mutation score = {pit_result.mutation_score:.2f}")
                return pit_result
            else:
                logger.error(f"PIT baseline failed: {error_output}")
                return PITResult(
                    test_class=test_class,
                    test_method=test_method,
                    mutation_score=0.0,
                    line_coverage=0.0,
                    mutants_killed=0,
                    mutants_survived=0,
                    total_mutants=0,
                    execution_time=execution_time,
                    pit_output=output,
                    success=False,
                    error_message=error_output
                )
                
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Exception during baseline PIT: {str(e)}")
            return PITResult(
                test_class=test_class,
                test_method=test_method,
                mutation_score=0.0,
                line_coverage=0.0,
                mutants_killed=0,
                mutants_survived=0,
                total_mutants=0,
                execution_time=execution_time,
                pit_output="",
                success=False,
                error_message=str(e)
            )
    
    def run_pit_refactored(self, test_class: str, original_method: str, 
                          refactored_method: str, refactored_code: str,
                          additional_imports: Optional[str] = None) -> PITResult:
        """
        Run PIT mutation testing on the refactored test method.
        
        Args:
            test_class: Fully qualified test class name
            original_method: Original test method name
            refactored_method: Refactored test method name
            refactored_code: Refactored test method code
            additional_imports: Additional imports needed
            
        Returns:
            PITResult with refactored test metrics
        """
        logger.info(f"Running refactored PIT for {test_class}.{refactored_method}")
        
        # Find test file
        test_file_path = self._find_test_file(test_class)
        if not test_file_path:
            return PITResult(
                test_class=test_class,
                test_method=refactored_method,
                mutation_score=0.0,
                line_coverage=0.0,
                mutants_killed=0,
                mutants_survived=0,
                total_mutants=0,
                execution_time=0.0,
                pit_output="",
                success=False,
                error_message=f"Test file not found for {test_class}"
            )
        
        # Backup original file
        self.backup_manager.backup([test_file_path])
        
        try:
            # Replace original method with refactored method
            self._replace_test_method(test_file_path, original_method, 
                                    refactored_method, refactored_code, additional_imports)
            
            # Run PIT on refactored method
            result = self.run_pit_baseline(test_class, refactored_method)
            
        finally:
            # Restore original file
            self.backup_manager.restore_file(test_file_path)
        
        return result
    
    def compare_pit_results(self, original: PITResult, 
                           refactored: PITResult, strategy: str) -> PITComparison:
        """
        Compare original and refactored PIT results.
        
        Args:
            original: Baseline PIT results
            refactored: Refactored test PIT results
            strategy: Refactoring strategy used
            
        Returns:
            PITComparison with improvement analysis
        """
        mutation_improvement = None
        coverage_improvement = None
        quality_assessment = "error"
        
        if original.success and refactored.success:
            mutation_improvement = refactored.mutation_score - original.mutation_score
            coverage_improvement = refactored.line_coverage - original.line_coverage
            
            # Determine overall quality improvement
            if mutation_improvement > 0.05:  # 5% threshold
                quality_assessment = "improved"
            elif mutation_improvement < -0.05:
                quality_assessment = "degraded"
            else:
                quality_assessment = "unchanged"
        
        return PITComparison(
            original=original,
            refactored=refactored
        )
    
    def save_pit_results(self, comparisons: List[PITComparison], 
                        project_name: str, strategy: str) -> Path:
        """
        Save PIT comparison results to CSV.
        
        Args:
            comparisons: List of PIT comparisons
            project_name: Name of the Java project
            strategy: Refactoring strategy
            
        Returns:
            Path to the saved CSV file
        """
        output_file = self.output_path / f"{project_name}_{strategy}_pit_results.csv"
        
        # Convert to DataFrame
        data = []
        for comp in comparisons:
            row = {
                'project_name': project_name,
                'test_class_name': comp.original.test_class,
                'test_method_name': comp.original.test_method,
                'strategy': strategy,
                'quality_improvement': comp.quality_improvement,
                'mutation_score_improvement': comp.mutation_score_improvement,
                'coverage_improvement': comp.coverage_improvement,
                
                # Original results
                'original_mutation_score': comp.original.mutation_score,
                'original_line_coverage': comp.original.line_coverage,
                'original_mutants_killed': comp.original.mutants_killed,
                'original_mutants_survived': comp.original.mutants_survived,
                'original_total_mutants': comp.original.total_mutants,
                'original_execution_time': comp.original.execution_time,
                'original_success': comp.original.success,
                'original_error': comp.original.error_message if not comp.original.success else None,
                
                # Refactored results
                'refactored_mutation_score': comp.refactored.mutation_score,
                'refactored_line_coverage': comp.refactored.line_coverage,
                'refactored_mutants_killed': comp.refactored.mutants_killed,
                'refactored_mutants_survived': comp.refactored.mutants_survived,
                'refactored_total_mutants': comp.refactored.total_mutants,
                'refactored_execution_time': comp.refactored.execution_time,
                'refactored_success': comp.refactored.success,
                'refactored_error': comp.refactored.error_message if not comp.refactored.success else None,
            }
            data.append(row)
        
        df = pd.DataFrame(data)
        df.to_csv(output_file, index=False)
        
        logger.info(f"PIT results saved to {output_file}")
        return output_file
    
    def _parse_pit_results(self, test_class: str, test_method: str, pit_output: str) -> PITResult:
        """Parse PIT XML/console output to extract metrics."""
        # TODO: Implement robust PIT output parsing
        # This is a simplified version - real implementation would parse XML results
        
        # For now, return mock results
        logger.warning("PIT result parsing not fully implemented - returning mock results")
        
        return PITResult(
            test_class=test_class,
            test_method=test_method,
            mutation_score=0.75,  # Mock value
            line_coverage=0.85,   # Mock value
            mutants_killed=15,    # Mock value
            mutants_survived=5,   # Mock value
            total_mutants=20,     # Mock value
            execution_time=0.0,
            pit_output=pit_output,
            success=True
        )
    
    def _find_test_file(self, test_class: str) -> Optional[Path]:
        """Find the Java test file for the given test class."""
        # Convert package.ClassName to path/ClassName.java
        class_path = test_class.replace('.', '/') + '.java'
        
        # Common test directories
        test_dirs = [
            'src/test/java',
            'test/java',
            'src/test',
            'test'
        ]
        
        for test_dir in test_dirs:
            potential_path = self.java_project_path / test_dir / class_path
            if potential_path.exists():
                return potential_path
        
        return None
    
    def _replace_test_method(self, test_file_path: Path, original_method: str,
                           refactored_method: str, refactored_code: str,
                           additional_imports: Optional[str] = None) -> None:
        """Replace original test method with refactored version."""
        # TODO: Implement robust method replacement
        # This is a simplified version
        
        logger.warning("Test method replacement not fully implemented")
        raise NotImplementedError("Test method replacement not yet implemented")