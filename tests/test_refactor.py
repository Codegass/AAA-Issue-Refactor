#!/usr/bin/env python3
"""Unit tests for refactor module."""

import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.refactor import PromptManager, TestRefactor, TestContext, RefactoringResult
from src.discovery import TestCase


class TestPromptManager(unittest.TestCase):
    """Test the PromptManager class."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.prompts_dir = Path(self.temp_dir)
        
        # Create prompt directories
        (self.prompts_dir / "system").mkdir()
        (self.prompts_dir / "refactoring").mkdir()
        
        # Create test prompt files
        (self.prompts_dir / "system" / "refactoring.md").write_text("System prompt for refactoring")
        (self.prompts_dir / "system" / "issue_checking.md").write_text("System prompt for issue checking")
        (self.prompts_dir / "refactoring" / "multiple_aaa.md").write_text("Refactoring prompt for Multiple AAA")
        
        self.prompt_manager = PromptManager(self.prompts_dir)
    
    def test_load_system_prompt_success(self):
        """Test loading system prompt successfully."""
        result = self.prompt_manager.load_system_prompt("refactoring")
        self.assertEqual(result, "System prompt for refactoring")
    
    def test_load_system_prompt_not_found(self):
        """Test loading system prompt that doesn't exist."""
        with self.assertRaises(FileNotFoundError):
            self.prompt_manager.load_system_prompt("nonexistent")
    
    def test_load_refactoring_prompt_success(self):
        """Test loading refactoring prompt successfully."""
        result = self.prompt_manager.load_refactoring_prompt("Multiple AAA")
        self.assertEqual(result, "Refactoring prompt for Multiple AAA")
    
    def test_load_refactoring_prompt_not_found(self):
        """Test loading refactoring prompt that doesn't exist."""
        with self.assertRaises(FileNotFoundError):
            self.prompt_manager.load_refactoring_prompt("Nonexistent Issue")
    
    def test_format_refactoring_user_prompt(self):
        """Test formatting refactoring user prompt."""
        context = TestContext(
            parsed_statements_sequence=["stmt1", "stmt2"],
            production_function_implementations=["impl1"],
            test_case_source_code="test code",
            imported_packages=["import1", "import2"],
            test_class_name="TestClass",
            test_case_name="testMethod",
            project_name="test-project",
            before_methods=["before1"],
            before_all_methods=["beforeAll1"],
            after_methods=["after1"],
            after_all_methods=["afterAll1"]
        )
        
        result = self.prompt_manager.format_refactoring_user_prompt(context, "Multiple AAA")
        
        self.assertIn("<Issue Type>Multiple AAA</Issue Type>", result)
        self.assertIn("<Test Case Source Code>test code</Test Case Source Code>", result)
        self.assertIn("<Test Case Import Packages>import1, import2</Test Case Import Packages>", result)
        self.assertIn("Refactoring prompt for Multiple AAA", result)
    
    def test_format_validation_user_prompt(self):
        """Test formatting validation user prompt."""
        context = TestContext(
            parsed_statements_sequence=[],
            production_function_implementations=["impl1"],
            test_case_source_code="original code",
            imported_packages=["import1"],
            test_class_name="TestClass",
            test_case_name="testMethod",
            project_name="test-project",
            before_methods=[],
            before_all_methods=[],
            after_methods=[],
            after_all_methods=[]
        )
        
        result = self.prompt_manager.format_validation_user_prompt(
            context, "refactored code", ["import1", "import2"], "Multiple AAA"
        )
        
        self.assertIn("<original issue type>Multiple AAA</original issue type>", result)
        self.assertIn("<Test Case Source Code>refactored code</Test Case Source Code>", result)
        self.assertIn("<Test Case Import Packages>import1, import2</Test Case Import Packages>", result)


class TestTestRefactor(unittest.TestCase):
    """Test the TestRefactor class."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.prompts_dir = Path(self.temp_dir) / "prompts"
        self.data_folder = Path(self.temp_dir) / "data"
        
        # Create directories
        self.prompts_dir.mkdir()
        (self.prompts_dir / "system").mkdir()
        (self.prompts_dir / "refactoring").mkdir()
        self.data_folder.mkdir()
        
        # Create prompt files
        (self.prompts_dir / "system" / "refactoring.md").write_text("System prompt")
        (self.prompts_dir / "system" / "issue_checking.md").write_text("Issue checking prompt")
        (self.prompts_dir / "refactoring" / "multiple_aaa.md").write_text("Multiple AAA prompt")
    
    @patch('src.refactor.LLMClient')
    def test_load_test_context_success(self, mock_llm_client):
        """Test loading test context successfully."""
        # Create test JSON file
        test_data = {
            "parsedStatementsSequence": ["stmt1"],
            "productionFunctionImplementations": ["impl1"],
            "testCaseSourceCode": "test code",
            "importedPackages": ["import1"],
            "testClassName": "TestClass",
            "testCaseName": "testMethod",
            "projectName": "test-project",
            "beforeMethods": [],
            "beforeAllMethods": [],
            "afterMethods": [],
            "afterAllMethods": []
        }
        
        json_file = self.data_folder / "test-project_TestClass_testMethod.json"
        with open(json_file, 'w') as f:
            json.dump(test_data, f)
        
        refactor = TestRefactor(self.prompts_dir, self.data_folder)
        context = refactor.load_test_context("test-project", "TestClass", "testMethod")
        
        self.assertEqual(context.test_case_source_code, "test code")
        self.assertEqual(context.test_class_name, "TestClass")
        self.assertEqual(context.project_name, "test-project")
    
    @patch('src.refactor.LLMClient')
    def test_load_test_context_not_found(self, mock_llm_client):
        """Test loading test context when file doesn't exist."""
        refactor = TestRefactor(self.prompts_dir, self.data_folder)
        
        with self.assertRaises(FileNotFoundError):
            refactor.load_test_context("test-project", "TestClass", "testMethod")
    
    def test_parse_refactoring_response_complete(self):
        """Test parsing complete refactoring response."""
        response = '''
<Refactored Test Case Source Code>
public void testMethod_refactored() {
    // Refactored code
}
</Refactored Test Case Source Code>
<Refactored Test Case Additional Import Packages>
import org.junit.Assume;
</Refactored Test Case Additional Import Packages>
<Refactoring Reasoning>
Changed the method to use assumptions instead of assertions.
</Refactoring Reasoning>
'''
        
        refactor = TestRefactor(self.prompts_dir, self.data_folder)
        result = refactor.parse_refactoring_response(response)
        
        self.assertIn("public void testMethod_refactored()", result["refactored_code"])
        self.assertEqual(result["additional_imports"], ["import org.junit.Assume;"])
        self.assertIn("assumptions instead of assertions", result["reasoning"])
    
    def test_parse_refactoring_response_case_insensitive(self):
        """Test parsing refactoring response with case variations."""
        response = '''
<refactored test case source code>
public void testMethod() { }
</refactored test case source code>
<REFACTORING_REASONING>
This is the reasoning.
</REFACTORING_REASONING>
'''
        
        refactor = TestRefactor(self.prompts_dir, self.data_folder)
        result = refactor.parse_refactoring_response(response)
        
        self.assertIn("public void testMethod()", result["refactored_code"])
        self.assertIn("This is the reasoning", result["reasoning"])
    
    def test_parse_validation_response_complete(self):
        """Test parsing complete validation response."""
        response = '''
<original issue type exists>false</original issue type exists>
<new issue type exists>true</new issue type exists>
<new issue type>Missing Assert</new issue type>
<reasoning>The original issue was fixed but a new issue was introduced.</reasoning>
'''
        
        refactor = TestRefactor(self.prompts_dir, self.data_folder)
        result = refactor.parse_validation_response(response)
        
        self.assertFalse(result["original_issue_exists"])
        self.assertTrue(result["new_issue_exists"])
        self.assertEqual(result["new_issue_type"], "Missing Assert")
        self.assertIn("original issue was fixed", result["reasoning"])
    
    def test_parse_boolean_variations(self):
        """Test parsing boolean values with different formats."""
        refactor = TestRefactor(self.prompts_dir, self.data_folder)
        
        # Test true values
        self.assertTrue(refactor._parse_boolean("true"))
        self.assertTrue(refactor._parse_boolean("YES"))
        self.assertTrue(refactor._parse_boolean("1"))
        self.assertTrue(refactor._parse_boolean("exists"))
        
        # Test false values
        self.assertFalse(refactor._parse_boolean("false"))
        self.assertFalse(refactor._parse_boolean("NO"))
        self.assertFalse(refactor._parse_boolean("0"))
        self.assertFalse(refactor._parse_boolean("absent"))
        
        # Test unknown values (should default to True for safety)
        self.assertTrue(refactor._parse_boolean("maybe"))
        self.assertTrue(refactor._parse_boolean("unknown"))


class TestTestContext(unittest.TestCase):
    """Test the TestContext dataclass."""
    
    def test_test_context_creation(self):
        """Test creating a TestContext object."""
        context = TestContext(
            parsed_statements_sequence=["stmt1", "stmt2"],
            production_function_implementations=["impl1"],
            test_case_source_code="test code",
            imported_packages=["import1", "import2"],
            test_class_name="TestClass",
            test_case_name="testMethod",
            project_name="test-project",
            before_methods=["before1"],
            before_all_methods=["beforeAll1"],
            after_methods=["after1"],
            after_all_methods=["afterAll1"]
        )
        
        self.assertEqual(context.test_case_source_code, "test code")
        self.assertEqual(context.test_class_name, "TestClass")
        self.assertEqual(len(context.imported_packages), 2)
        self.assertEqual(len(context.parsed_statements_sequence), 2)


class TestRefactoringResult(unittest.TestCase):
    """Test the RefactoringResult dataclass."""
    
    def test_refactoring_result_success(self):
        """Test creating a successful refactoring result."""
        result = RefactoringResult(
            success=True,
            refactored_code="public void test() { }",
            additional_imports=["import org.junit.Test;"],
            reasoning="Fixed the issue",
            iterations=2,
            tokens_used=100,
            cost=0.01,
            processing_time=5.0
        )
        
        self.assertTrue(result.success)
        self.assertEqual(result.refactored_code, "public void test() { }")
        self.assertEqual(result.iterations, 2)
        self.assertIsNone(result.error_message)
    
    def test_refactoring_result_failure(self):
        """Test creating a failed refactoring result."""
        result = RefactoringResult(
            success=False,
            error_message="Failed to parse response",
            iterations=1,
            processing_time=2.0
        )
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_message, "Failed to parse response")
        self.assertIsNone(result.refactored_code)


if __name__ == '__main__':
    unittest.main()