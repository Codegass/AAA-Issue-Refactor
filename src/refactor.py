"""Main refactoring orchestration logic."""

import json
import time
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import logging

from .llm_client import LLMClient
from .discovery import TestCase
from .sanitizer import Sanitizer

logger = logging.getLogger('aif')

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
    refactored_method_names: Optional[List[str]] = field(default_factory=list)
    additional_imports: Optional[List[str]] = field(default_factory=list)
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
    
    def _analyze_frameworks(self, imports: List[str], source_code: str) -> str:
        """Analyzes import statements to identify testing and mocking frameworks."""
        frameworks = []
        # Test Frameworks
        if any("org.junit.jupiter" in imp for imp in imports):
            frameworks.append("JUnit 5")
        elif any("org.junit.Test" in imp for imp in imports):
            frameworks.append("JUnit 4")
        elif "extends TestCase" in source_code and any("junit.framework.TestCase" in imp for imp in imports):
            frameworks.append("JUnit 3")
        
        if any("org.testng" in imp for imp in imports):
            frameworks.append("TestNG")

        # Mock Frameworks
        if any("org.mockito" in imp for imp in imports):
            frameworks.append("Mockito")
        if any("org.easymock" in imp for imp in imports):
            frameworks.append("EasyMock")
            
        if not frameworks:
            return "Unknown"
        
        return " and ".join(frameworks)

    def format_refactoring_user_prompt(self, context: TestContext, issue_type: str) -> str:
        """Format the user prompt for refactoring."""
        refactoring_prompt = self.load_refactoring_prompt(issue_type)
        frameworks = self._analyze_frameworks(context.imported_packages, context.test_case_source_code)
        
        return f"""<Issue Type>{issue_type}</Issue Type>
<Test Frameworks>{frameworks}</Test Frameworks>
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
    
    def __init__(self, prompts_dir: Path, data_folder_path: Path, rftype: str):
        self.prompt_manager = PromptManager(prompts_dir / f"v1-{rftype}")
        self.data_folder_path = data_folder_path
        self.llm_client = LLMClient()
        self.sanitizer = Sanitizer()
    
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
        """Parse LLM refactoring response with robust XML tag extraction, returning raw code."""
        result = {
            "raw_refactored_code": "",
            "additional_imports": [],
            "reasoning": ""
        }
        
        # Extract refactored code (raw)
        refactored_code = self._extract_xml_content(response, "Refactored Test Case Source Code")
        if refactored_code:
            result["raw_refactored_code"] = refactored_code
        
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
    
    def _extract_method_names(self, code: str) -> List[str]:
        """
        Extracts all method names from a block of Java code that are annotated with @Test.
        This regex is designed to be robust by:
        1. Anchoring to the start of a line (`re.MULTILINE`).
        2. Allowing for other annotations between @Test and the method signature (`re.DOTALL`).
        3. Handling various modifiers (public, static, etc.).
        4. Greatly reducing the chance of matching @Test inside comments or string literals.
        """
        # It finds a line starting with @Test, lazily consumes until `void`, then captures the method name.
        pattern = re.compile(
            r"^\s*@Test.*?\s+void\s+([a-zA-Z_]\w*)\s*\(",
            re.MULTILINE | re.DOTALL
        )
        return pattern.findall(code)

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
    
    def refactor_test_case(self, test_case: TestCase, debug_mode: bool = False, max_refinement_loops: int = 5) -> RefactoringResult:
        """
        Refactors a single test case using a two-loop process.
        - Outer loop: Validation-driven refinement (max 5 iterations).
        - Inner loop: Code sanitization to get a clean response (max 3 retries).
        """
        start_time = time.time()
        
        try:
            context = self.load_test_context(
                test_case.project_name,
                test_case.test_class_name,
                test_case.test_method_name
            )
            
            refactoring_system_prompt = self.prompt_manager.load_system_prompt("refactoring")
            validation_system_prompt = self.prompt_manager.load_system_prompt("issue_checking")
            
            self.llm_client.reset_usage_stats()
            
            # --- State for the outer refinement loop ---
            refactoring_session_messages = []
            validation_feedback_for_refactoring = ""
            
            # --- Outer loop for validation-driven refinement ---
            for loop_num in range(max_refinement_loops):
                
                # --- Inner loop to get a clean, well-formatted response ---
                max_sanitizer_retries = 3
                sanitized_code = ""
                parsed_llm_result = {}

                for attempt in range(max_sanitizer_retries):
                    logger.debug(f"Refinement loop {loop_num + 1}/{max_refinement_loops}, Sanitizer attempt {attempt + 1}/{max_sanitizer_retries}")
                    
                    user_prompt = self.prompt_manager.format_refactoring_user_prompt(context, test_case.issue_type)
                    
                    # Add feedback from the previous validation loop to the user prompt
                    if validation_feedback_for_refactoring:
                        user_prompt += f"\n<Validation Feedback>{validation_feedback_for_refactoring}</Validation Feedback>"

                    # Create a temporary list of messages for this specific API call
                    current_call_messages = refactoring_session_messages + [{"role": "user", "content": user_prompt}]

                    # 1. Refactoring API Call
                    refactoring_response = self.llm_client.send_chat_request(refactoring_system_prompt, current_call_messages)
                    
                    # 2. Parse and Sanitize
                    raw_parsed = self.parse_refactoring_response(refactoring_response)
                    sanitized_code = self.sanitizer.clean_code(raw_parsed.get("raw_refactored_code", ""))
                    
                    # 3. Check sanitization quality
                    if self.sanitizer.was_last_clean_successful(raw_parsed.get("raw_refactored_code", ""), sanitized_code):
                        parsed_llm_result = raw_parsed
                        
                        # Add the successful exchange to our main refactoring history
                        refactoring_session_messages.append({"role": "user", "content": user_prompt})
                        refactoring_session_messages.append({"role": "assistant", "content": refactoring_response})
                        break
                    else:
                        logger.warning(f"  ⚠ Sanitizer made significant changes. Retrying LLM call... (Attempt {attempt + 2}/{max_sanitizer_retries})")
                        time.sleep(1)

                if not sanitized_code:
                    return RefactoringResult(
                        success=False, error_message=f"Failed to get a clean response from LLM after {max_sanitizer_retries} attempts.",
                        iterations=loop_num + 1, processing_time=time.time() - start_time
                    )
                
                # --- End of inner sanitizer loop. We now have good, sanitized code. ---
                logger.debug(f"\n--- Sanitized Code (Loop {loop_num+1}) ---\n{sanitized_code}\n---")
                
                # 4. Validate the sanitized code
                all_imports = context.imported_packages + parsed_llm_result.get("additional_imports", [])
                validation_prompt = self.prompt_manager.format_validation_user_prompt(context, sanitized_code, all_imports, test_case.issue_type)
                
                # The validation session is independent and stateless
                validation_response = self.llm_client.send_chat_request(validation_system_prompt, [{"role": "user", "content": validation_prompt}])
                validation_result = self.parse_validation_response(validation_response)
                
                if debug_mode:
                    logger.debug(f"--- Validation Response (Loop {loop_num+1}) ---\n{validation_response}\n---")
                    logger.debug(f"Parsed validation: {validation_result}")

                # 5. Check if refactoring is complete
                if not validation_result["original_issue_exists"] and not validation_result["new_issue_exists"]:
                    logger.info("  ✓ Validation successful. Refactoring complete.")
                    usage_stats = self.llm_client.get_usage_stats()
                    return RefactoringResult(
                        success=True,
                        refactored_code=sanitized_code,
                        refactored_method_names=self._extract_method_names(sanitized_code),
                        additional_imports=parsed_llm_result.get("additional_imports", []),
                        reasoning=parsed_llm_result.get("reasoning", ""),
                        iterations=loop_num + 1,
                        chat_history=json.dumps(refactoring_session_messages, indent=2),
                        tokens_used=usage_stats["total_tokens"],
                        cost=usage_stats["total_cost"],
                        processing_time=time.time() - start_time
                    )
                
                # 6. If issues persist, prepare feedback for the next loop
                logger.info(f"  - Validation failed on loop {loop_num + 1}. Preparing feedback for retry...")
                validation_feedback_for_refactoring = validation_result.get("reasoning", "The previous attempt was not correct. Please try again.")
                if debug_mode:
                    logger.debug(f"Feedback for next loop: {validation_feedback_for_refactoring}")
                context.test_case_source_code = sanitized_code # Use the failed code as basis for next attempt
            
            # Max outer loops reached without success
            usage_stats = self.llm_client.get_usage_stats()
            return RefactoringResult(
                success=False, error_message=f"Maximum refinement loops ({max_refinement_loops}) reached without success.",
                iterations=max_refinement_loops, chat_history=json.dumps(refactoring_session_messages, indent=2),
                tokens_used=usage_stats["total_tokens"], cost=usage_stats["total_cost"],
                processing_time=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"  ✗ An unexpected error occurred during refactoring: {e}", exc_info=debug_mode)
            usage_stats = self.llm_client.get_usage_stats()
            return RefactoringResult(
                success=False, error_message=str(e),
                iterations=0, # Or pass loop_num if you can
                tokens_used=usage_stats["total_tokens"], cost=usage_stats["total_cost"],
                processing_time=time.time() - start_time
            )