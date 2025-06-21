#!/usr/bin/env python3
"""Unit tests for discovery module."""

import unittest
import tempfile
import csv
from pathlib import Path
from unittest.mock import patch, mock_open

from src.discovery import TestDiscovery, TestCase


class TestTestCase(unittest.TestCase):
    """Test the TestCase class."""
    
    def test_test_case_creation(self):
        """Test creating a TestCase object."""
        test_case = TestCase("commons-cli", "org.apache.commons.cli.OptionTest", "testSubclass", "Good AAA")
        
        self.assertEqual(test_case.project_name, "commons-cli")
        self.assertEqual(test_case.test_class_name, "org.apache.commons.cli.OptionTest")
        self.assertEqual(test_case.test_method_name, "testSubclass")
        self.assertEqual(test_case.issue_type, "Good AAA")
        self.assertIsNone(test_case.test_path)
        self.assertIsNone(test_case.test_case_loc)
        self.assertEqual(test_case.runable, "no")
        self.assertEqual(test_case.pass_status, "no")


class TestTestDiscovery(unittest.TestCase):
    """Test the TestDiscovery class."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.java_project_path = Path(self.temp_dir) / "java_project"
        self.data_folder_path = Path(self.temp_dir) / "data"
        
        # Create directories
        self.java_project_path.mkdir()
        self.data_folder_path.mkdir()
        
        self.discovery = TestDiscovery(self.java_project_path, self.data_folder_path)
    
    def test_load_aaa_results_csv_found(self):
        """Test loading AAA results when CSV file exists."""
        # Create a test CSV file
        csv_content = '''project,class_name,test_case_name,issue_type,sequence,focal_method,reasoning
commons-cli,org.apache.commons.cli.OptionTest,testSubclass,Good AAA,Arrange → Act → Assert,Option.clone(),Test reasoning
commons-cli,org.apache.commons.cli.help.UtilTest,testIsEmpty,Multiple AAA,Multiple sequences,Util.isEmpty,Multiple scenarios'''
        
        csv_file = self.data_folder_path / "commons-cli AAAResults.csv"
        with open(csv_file, 'w', encoding='utf-8') as f:
            f.write(csv_content)
        
        test_cases = self.discovery.load_aaa_results()
        
        self.assertEqual(len(test_cases), 2)
        self.assertEqual(test_cases[0].project_name, "commons-cli")
        self.assertEqual(test_cases[0].test_class_name, "org.apache.commons.cli.OptionTest")
        self.assertEqual(test_cases[0].test_method_name, "testSubclass")
        self.assertEqual(test_cases[0].issue_type, "Good AAA")
        
        self.assertEqual(test_cases[1].issue_type, "Multiple AAA")
    
    def test_load_aaa_results_no_csv(self):
        """Test loading AAA results when no CSV file exists."""
        with self.assertRaises(FileNotFoundError):
            self.discovery.load_aaa_results()
    
    def test_find_test_file_found(self):
        """Test finding a test file that exists."""
        # Create test directory structure
        test_dir = self.java_project_path / "src" / "test" / "java" / "org" / "apache" / "commons" / "cli"
        test_dir.mkdir(parents=True)
        
        test_file = test_dir / "OptionTest.java"
        test_file.write_text("public class OptionTest { }")
        
        result = self.discovery.find_test_file("org.apache.commons.cli.OptionTest")
        
        self.assertEqual(result, test_file)
    
    def test_find_test_file_not_found(self):
        """Test finding a test file that doesn't exist."""
        result = self.discovery.find_test_file("org.apache.commons.cli.NonExistentTest")
        
        self.assertIsNone(result)
    
    def test_count_lines_of_code(self):
        """Test counting lines of code for a method."""
        java_content = '''public class TestClass {
    
    @Test
    public void testMethod() {
        String value = "test";
        assertEquals("test", value);
        // Comment line
        assertTrue(true);
    }
    
    public void anotherMethod() {
        // Other method
    }
}'''
        
        test_file = self.java_project_path / "TestClass.java"
        test_file.write_text(java_content)
        
        loc = self.discovery.count_lines_of_code(test_file, "testMethod")
        
        # Should count non-empty, non-comment lines within the method
        self.assertGreater(loc, 0)
    
    def test_validate_test_cases(self):
        """Test validating test cases."""
        # Create test case
        test_case = TestCase("commons-cli", "org.apache.commons.cli.OptionTest", "testSubclass", "Good AAA")
        
        # Create test file
        test_dir = self.java_project_path / "src" / "test" / "java" / "org" / "apache" / "commons" / "cli"
        test_dir.mkdir(parents=True)
        test_file = test_dir / "OptionTest.java"
        test_file.write_text("public class OptionTest { public void testSubclass() { } }")
        
        validated_cases = self.discovery.validate_test_cases([test_case])
        
        self.assertEqual(len(validated_cases), 1)
        self.assertEqual(validated_cases[0].runable, "yes")
        self.assertIsNotNone(validated_cases[0].test_path)
        self.assertGreater(validated_cases[0].test_case_loc, 0)
    
    def test_save_refactor_cases_csv(self):
        """Test saving refactor cases to CSV."""
        test_case = TestCase("commons-cli", "org.apache.commons.cli.OptionTest", "testSubclass", "Good AAA")
        test_case.test_path = "/path/to/test"
        test_case.test_case_loc = 10
        test_case.runable = "yes"
        test_case.pass_status = "unknown"
        
        self.discovery.save_refactor_cases_csv([test_case], Path(self.temp_dir))
        
        csv_file = Path(self.temp_dir) / "commons-cli_AAA_Refactor_Cases.csv"
        self.assertTrue(csv_file.exists())
        
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['project_name'], 'commons-cli')
        self.assertEqual(rows[0]['test_class_name'], 'org.apache.commons.cli.OptionTest')
        self.assertEqual(rows[0]['issue_type'], 'Good AAA')


if __name__ == '__main__':
    unittest.main()