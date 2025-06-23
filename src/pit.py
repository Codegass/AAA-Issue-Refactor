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

from .executor import CommandExecutor
from .utils import BackupManager

logger = logging.getLogger('aif.pit')


@dataclass
class PITResult:
    """Results from a PIT mutation testing run."""
    test_class: str
    test_method: str
    mutation_score: float
    line_coverage: float
    mutants_killed: int
    mutants_survived: int
    total_mutants: int
    execution_time: float
    pit_output: str
    success: bool
    error_message: Optional[str] = None


@dataclass
class PITComparison:
    """Comparison between original and refactored test PIT results."""
    project_name: str
    test_class_name: str
    test_method_name: str
    strategy: str
    original_result: Optional[PITResult]
    refactored_result: Optional[PITResult]
    mutation_score_improvement: Optional[float]
    coverage_improvement: Optional[float]
    quality_improvement: str  # "improved", "degraded", "unchanged", "error"


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
        
        # Detect build system
        self.build_system = self._detect_build_system()
        logger.info(f"Detected build system: {self.build_system}")
    
    def _detect_build_system(self) -> str:
        """Detect whether the project uses Maven or Gradle."""
        if (self.java_project_path / "pom.xml").exists():
            return "maven"
        elif (self.java_project_path / "build.gradle").exists() or \
             (self.java_project_path / "build.gradle.kts").exists():
            return "gradle"
        else:
            raise ValueError("Could not detect Maven or Gradle build system")
    
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
            if self.build_system == "maven":
                command = [
                    "mvn", "org.pitest:pitest-maven:mutationCoverage",
                    f"-DtargetClasses={test_class.replace('.', '/')}*",
                    f"-DtargetTests={test_class}.{test_method}",
                    "-DoutputFormats=XML,HTML",
                    "-DwithHistory=false"
                ]
            else:  # gradle
                command = [
                    "./gradlew", "pitest",
                    f"-PtargetClasses={test_class.replace('.', '/')}*",
                    f"-PtargetTests={test_class}.{test_method}"
                ]
            
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
            project_name=original.test_class.split('.')[0] if '.' in original.test_class else "unknown",
            test_class_name=original.test_class,
            test_method_name=original.test_method,
            strategy=strategy,
            original_result=original,
            refactored_result=refactored,
            mutation_score_improvement=mutation_improvement,
            coverage_improvement=coverage_improvement,
            quality_improvement=quality_assessment
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
                'project_name': comp.project_name,
                'test_class_name': comp.test_class_name,
                'test_method_name': comp.test_method_name,
                'strategy': comp.strategy,
                'quality_improvement': comp.quality_improvement,
                'mutation_score_improvement': comp.mutation_score_improvement,
                'coverage_improvement': comp.coverage_improvement,
                
                # Original results
                'original_mutation_score': comp.original_result.mutation_score if comp.original_result else None,
                'original_line_coverage': comp.original_result.line_coverage if comp.original_result else None,
                'original_mutants_killed': comp.original_result.mutants_killed if comp.original_result else None,
                'original_mutants_survived': comp.original_result.mutants_survived if comp.original_result else None,
                'original_total_mutants': comp.original_result.total_mutants if comp.original_result else None,
                'original_execution_time': comp.original_result.execution_time if comp.original_result else None,
                'original_success': comp.original_result.success if comp.original_result else False,
                'original_error': comp.original_result.error_message if comp.original_result else None,
                
                # Refactored results
                'refactored_mutation_score': comp.refactored_result.mutation_score if comp.refactored_result else None,
                'refactored_line_coverage': comp.refactored_result.line_coverage if comp.refactored_result else None,
                'refactored_mutants_killed': comp.refactored_result.mutants_killed if comp.refactored_result else None,
                'refactored_mutants_survived': comp.refactored_result.mutants_survived if comp.refactored_result else None,
                'refactored_total_mutants': comp.refactored_result.total_mutants if comp.refactored_result else None,
                'refactored_execution_time': comp.refactored_result.execution_time if comp.refactored_result else None,
                'refactored_success': comp.refactored_result.success if comp.refactored_result else False,
                'refactored_error': comp.refactored_result.error_message if comp.refactored_result else None,
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