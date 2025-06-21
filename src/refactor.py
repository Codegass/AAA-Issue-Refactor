"""Main refactoring orchestration logic."""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from .llm_client import LLMClient
from .discovery import TestCase

@dataclass
class TestContext:
    """Container for test case context information."""
    parsed_statements_sequence: List[str]
    production_function_implementations: List[str]
    test_case_source_code: str
    imported_packages: List[str]
    test_class_name: str
    test_case_name: str
    project_name: str
    before_methods: List[str]
    before_all_methods: List[str]
    after_methods: List[str]
    after_all_methods: List[str]

@dataclass
class RefactoringResult:
    """Result of a refactoring operation."""
    success: bool
    refactored_code: Optional[str] = None
    additional_imports: Optional[List[str]] = None
    reasoning: Optional[str] = None
    iterations: int = 0
    error_message: Optional[str] = None
    chat_history: Optional[str] = None
    tokens_used: int = 0
    cost: float = 0.0
    processing_time: float = 0.0

class PromptManager:
    """Manages loading and formatting of prompts."""
    
    def __init__(self, prompts_dir: Path):
        self.prompts_dir = prompts_dir
    
    def load_system_prompt(self, prompt_type: str) -> str:
        """Load system prompt from file."""
        path = self.prompts_dir / "system" / f"{prompt_type}.md"
        if not path.exists():
            raise FileNotFoundError(f"System prompt not found: {path}")
        return path.read_text(encoding='utf-8')
    
    def load_refactoring_prompt(self, issue_type: str) -> str:
        """Load issue-specific refactoring prompt."""
        # Handle combined issue types by taking the first (primary) issue
        primary_issue = issue_type.split(',')[0].strip().strip('[]')
        
        # Convert issue type to filename format with special mappings
        filename_mappings = {
            "assert pre-condition": "assert_precondition",
            "arrange & quit": "arrange_quit", 
            "multiple aaa": "multiple_aaa",
            "missing assert": "missing_assert",
            "obscure assert": "obscure_assert",
            "multiple acts": "multiple_acts",
            "suppressed exception": "suppressed_exception"
        }
        
        normalized_issue = primary_issue.lower()
        filename = filename_mappings.get(normalized_issue, normalized_issue.replace(" ", "_").replace("-", "_"))
        filename += ".md"
        
        path = self.prompts_dir / "refactoring" / filename
        if not path.exists():
            raise FileNotFoundError(f"Refactoring prompt not found: {path}")
        return path.read_text(encoding='utf-8')
    
    def format_refactoring_user_prompt(self, context: TestContext, issue_type: str) -> str:
        """Format the user prompt for refactoring."""
        refactoring_prompt = self.load_refactoring_prompt(issue_type)
        
        return f"""<Issue Type>{issue_type}</Issue Type>
<Test Case Source Code>{context.test_case_source_code}</Test Case Source Code>
<Test Case Import Packages>{', '.join(context.imported_packages)}</Test Case Import Packages>
<Production Function Implementations>{', '.join(context.production_function_implementations)}</Production Function Implementations>
<Test Case Before Methods>{', '.join(context.before_methods)}</Test Case Before Methods>
<Test Case After Methods>{', '.join(context.after_methods)}</Test Case After Methods>
<Test Case Before All Methods>{', '.join(context.before_all_methods)}</Test Case Before All Methods>
<Test Case After All Methods>{', '.join(context.after_all_methods)}</Test Case After All Methods>
<Refactoring Prompt>{refactoring_prompt}</Refactoring Prompt>"""
    
    def format_validation_user_prompt(self, context: TestContext, refactored_code: str, all_imports: List[str], original_issue: str) -> str:
        """Format the user prompt for validation."""
        return f"""<original issue type>{original_issue}</original issue type>
<Test Case Source Code>{refactored_code}</Test Case Source Code>
<Test Case Import Packages>{', '.join(all_imports)}</Test Case Import Packages>
<Production Function Implementations>{', '.join(context.production_function_implementations)}</Production Function Implementations>
<Test Case Before Methods>{', '.join(context.before_methods)}</Test Case Before Methods>
<Test Case After Methods>{', '.join(context.after_methods)}</Test Case After Methods>
<Test Case Before All Methods>{', '.join(context.before_all_methods)}</Test Case Before All Methods>
<Test Case After All Methods>{', '.join(context.after_all_methods)}</Test Case After All Methods>"""

class TestRefactor:
    """Main test refactoring orchestrator."""
    
    def __init__(self, prompts_dir: Path, data_folder_path: Path):
        self.prompt_manager = PromptManager(prompts_dir)
        self.data_folder_path = data_folder_path
        self.llm_client = LLMClient()
    
    def load_test_context(self, project_name: str, test_class: str, test_method: str) -> TestContext:
        """Load test context from JSON file."""
        json_filename = f"{project_name}_{test_class}_{test_method}.json"
        json_path = self.data_folder_path / json_filename
        
        if not json_path.exists():
            raise FileNotFoundError(f"Test context JSON not found: {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return TestContext(
            parsed_statements_sequence=data.get("parsedStatementsSequence", []),
            production_function_implementations=data.get("productionFunctionImplementations", []),
            test_case_source_code=data.get("testCaseSourceCode", ""),
            imported_packages=data.get("importedPackages", []),
            test_class_name=data.get("testClassName", ""),
            test_case_name=data.get("testCaseName", ""),
            project_name=data.get("projectName", ""),
            before_methods=data.get("beforeMethods", []),
            before_all_methods=data.get("beforeAllMethods", []),
            after_methods=data.get("afterMethods", []),
            after_all_methods=data.get("afterAllMethods", [])
        )
    
    def parse_refactoring_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM refactoring response with robust XML tag extraction."""
        result = {
            "refactored_code": "",
            "additional_imports": [],
            "reasoning": ""
        }
        
        # Extract refactored code
        refactored_code = self._extract_xml_content(response, "Refactored Test Case Source Code")
        if refactored_code:
            result["refactored_code"] = refactored_code
        
        # Extract additional imports
        imports_text = self._extract_xml_content(response, "Refactored Test Case Additional Import Packages")
        if imports_text:
            # Handle both comma-separated and newline-separated imports
            imports = []
            for line in imports_text.replace(',', '\n').split('\n'):
                clean_import = line.strip()
                if clean_import and not clean_import.lower() in ['none', 'n/a', 'empty']:
                    imports.append(clean_import)
            result["additional_imports"] = imports
        
        # Extract reasoning
        reasoning = self._extract_xml_content(response, "Refactoring Reasoning")
        if reasoning:
            result["reasoning"] = reasoning
        
        return result
    
    def _extract_xml_content(self, text: str, tag_name: str) -> str:
        """Extract content between XML-like tags with fallback strategies."""
        # Try exact match first
        start_tag = f"<{tag_name}>"
        end_tag = f"</{tag_name}>"
        
        start_idx = text.find(start_tag)
        if start_idx != -1:
            start_idx += len(start_tag)
            end_idx = text.find(end_tag, start_idx)
            if end_idx != -1:
                return text[start_idx:end_idx].strip()
        
        # Try case-insensitive match
        start_tag_lower = start_tag.lower()
        end_tag_lower = end_tag.lower()
        text_lower = text.lower()
        
        start_idx = text_lower.find(start_tag_lower)
        if start_idx != -1:
            start_idx += len(start_tag_lower)
            end_idx = text_lower.find(end_tag_lower, start_idx)
            if end_idx != -1:
                return text[start_idx:end_idx].strip()
        
        # Try with variations (spaces, underscores)
        tag_variations = [
            tag_name.replace(" ", "_"),
            tag_name.replace(" ", ""),
            tag_name.replace("_", " ")
        ]
        
        for variant in tag_variations:
            start_tag_var = f"<{variant}>"
            end_tag_var = f"</{variant}>"
            start_idx = text.lower().find(start_tag_var.lower())
            if start_idx != -1:
                start_idx += len(start_tag_var)
                end_idx = text.lower().find(end_tag_var.lower(), start_idx)
                if end_idx != -1:
                    return text[start_idx:end_idx].strip()
        
        return ""
    
    def parse_validation_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM validation response with robust parsing."""
        result = {
            "original_issue_exists": True,
            "new_issue_exists": False,
            "new_issue_type": "",
            "reasoning": ""
        }
        
        # Extract original issue existence
        original_exists_text = self._extract_xml_content(response, "original issue type exists")
        if original_exists_text:
            result["original_issue_exists"] = self._parse_boolean(original_exists_text)
        
        # Extract new issue existence
        new_exists_text = self._extract_xml_content(response, "new issue type exists")
        if new_exists_text:
            result["new_issue_exists"] = self._parse_boolean(new_exists_text)
        
        # Extract new issue type
        new_issue_type = self._extract_xml_content(response, "new issue type")
        if new_issue_type:
            result["new_issue_type"] = new_issue_type
        
        # Extract reasoning
        reasoning = self._extract_xml_content(response, "reasoning")
        if reasoning:
            result["reasoning"] = reasoning
        
        return result
    
    def _parse_boolean(self, text: str) -> bool:
        """Parse boolean values with various formats."""
        text = text.lower().strip()
        true_values = ['true', 'yes', '1', 'exists', 'present']
        false_values = ['false', 'no', '0', 'not exists', 'absent', 'none']
        
        if text in true_values:
            return True
        elif text in false_values:
            return False
        else:
            # Default to True for safety (assume issue exists if unclear)
            return True
    
    def refactor_test_case(self, test_case: TestCase, max_iterations: int = 5) -> RefactoringResult:
        """Refactor a single test case with iterative improvement."""
        start_time = time.time()
        chat_history = []
        
        try:
            # Load test context
            context = self.load_test_context(
                test_case.project_name,
                test_case.test_class_name,
                test_case.test_method_name
            )
            
            # Load prompts
            refactoring_system_prompt = self.prompt_manager.load_system_prompt("refactoring")
            validation_system_prompt = self.prompt_manager.load_system_prompt("issue_checking")
            
            current_code = context.test_case_source_code
            current_imports = context.imported_packages.copy()
            iterations = 0
            
            for iteration in range(max_iterations):
                iterations += 1
                
                # Refactoring step
                user_prompt = self.prompt_manager.format_refactoring_user_prompt(context, test_case.issue_type)
                refactoring_response = self.llm_client.refactor_test_case(refactoring_system_prompt, user_prompt)
                
                chat_history.append(f"Iteration {iteration + 1} - Refactoring:")
                chat_history.append(f"User: {user_prompt}")
                chat_history.append(f"Assistant: {refactoring_response}")
                
                # Parse refactoring response
                refactoring_result = self.parse_refactoring_response(refactoring_response)
                
                if not refactoring_result["refactored_code"]:
                    return RefactoringResult(
                        success=False,
                        error_message="Failed to extract refactored code from LLM response",
                        iterations=iterations,
                        chat_history='\n'.join(chat_history),
                        processing_time=time.time() - start_time
                    )
                
                current_code = refactoring_result["refactored_code"]
                if refactoring_result["additional_imports"]:
                    current_imports.extend(refactoring_result["additional_imports"])
                
                # Validation step
                validation_prompt = self.prompt_manager.format_validation_user_prompt(
                    context, current_code, current_imports, test_case.issue_type
                )
                validation_response = self.llm_client.validate_refactored_code(validation_system_prompt, validation_prompt)
                
                chat_history.append(f"Iteration {iteration + 1} - Validation:")
                chat_history.append(f"User: {validation_prompt}")
                chat_history.append(f"Assistant: {validation_response}")
                
                # Parse validation response
                validation_result = self.parse_validation_response(validation_response)
                
                # Check if refactoring is successful
                if not validation_result["original_issue_exists"] and not validation_result["new_issue_exists"]:
                    # Success!
                    usage_stats = self.llm_client.get_usage_stats()
                    return RefactoringResult(
                        success=True,
                        refactored_code=current_code,
                        additional_imports=refactoring_result["additional_imports"],
                        reasoning=refactoring_result["reasoning"],
                        iterations=iterations,
                        chat_history='\n'.join(chat_history),
                        tokens_used=usage_stats["total_tokens"],
                        cost=usage_stats["total_cost"],
                        processing_time=time.time() - start_time
                    )
                
                # If we have new issues or the original issue persists, continue iterating
                if iteration < max_iterations - 1:
                    # Update context for next iteration with validation feedback
                    context.test_case_source_code = current_code
                    context.imported_packages = current_imports
            
            # Max iterations reached without success
            usage_stats = self.llm_client.get_usage_stats()
            return RefactoringResult(
                success=False,
                error_message="Maximum iterations reached without successful refactoring",
                iterations=iterations,
                chat_history='\n'.join(chat_history),
                tokens_used=usage_stats["total_tokens"],
                cost=usage_stats["total_cost"],
                processing_time=time.time() - start_time
            )
            
        except Exception as e:
            usage_stats = self.llm_client.get_usage_stats()
            return RefactoringResult(
                success=False,
                error_message=str(e),
                iterations=iterations,
                chat_history='\n'.join(chat_history),
                tokens_used=usage_stats["total_tokens"],
                cost=usage_stats["total_cost"],
                processing_time=time.time() - start_time
            )