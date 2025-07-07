"""Main refactoring orchestration logic."""

import json
import time
import re
import pandas as pd
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import logging
import yaml

from .llm_client import LLMClient
from .discovery import TestCase
from .sanitizer import Sanitizer
from .usage_tracker import UsageTracker
from .import_manager import SmartImportManager

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
    
    def __init__(self, prompts_dir: Path, rftype: str = ""):
        self.prompts_dir = prompts_dir
        self.rftype = rftype
    
    def load_system_prompt(self, prompt_type: str) -> str:
        """Load system prompt from file."""
        path = self.prompts_dir / "system" / f"{prompt_type}.md"
        if not path.exists():
            raise FileNotFoundError(f"System prompt not found: {path}")
        return path.read_text(encoding='utf-8')
    
    def load_refactoring_prompt(self, issue_type: str) -> str:
        """Load issue-specific refactoring prompt(s). Handles multiple issue types."""
        # Parse multiple issue types (comma or semicolon separated)
        issue_types = []
        for separator in [',', ';']:
            if separator in issue_type:
                issue_types = [issue.strip().strip('[]') for issue in issue_type.split(separator)]
                break
        
        if not issue_types:
            # Single issue type
            issue_types = [issue_type.strip().strip('[]')]
        
        # Load prompts for each issue type
        prompts = []
        for idx, single_issue in enumerate(issue_types):
            try:
                prompt = self._load_single_issue_prompt(single_issue)
                prompts.append(f"### Issue Type {idx + 1}: {single_issue}\n{prompt}")
            except FileNotFoundError as e:
                logger.warning(f"Prompt not found for issue '{single_issue}': {e}")
                # Continue with other issues, don't fail completely
                continue
        
        if not prompts:
            raise FileNotFoundError(f"No prompts found for any issue types in '{issue_type}'")
        
        if len(prompts) == 1:
            # Single issue, return the prompt directly without numbering
            # For DSL, the header is already part of the formatted YAML, so we don't split
            if "v2-dsl-aaa" in str(self.prompts_dir):
                return prompts[0]
            return prompts[0].split('\n', 1)[1]  # Remove the "Issue Type 1:" header
        else:
            # Multiple issues, combine them
            combined_prompt = "This test case has multiple AAA issues that need to be addressed:\n\n"
            combined_prompt += "\n\n".join(prompts)
            combined_prompt += "\n\nPlease refactor the test case to address ALL identified issues comprehensively."
            return combined_prompt
    
    def _load_single_issue_prompt(self, issue_type: str) -> str:
        """Load prompt for a single issue type from .md or .yml file."""
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
        
        normalized_issue = issue_type.lower()
        base_filename = filename_mappings.get(normalized_issue, normalized_issue.replace(" ", "_").replace("-", "_"))
        
        # Determine file type and handling based on strategy path
        if "v2-dsl-aaa" in str(self.prompts_dir):
            filename = base_filename + ".yml"
            path = self.prompts_dir / "refactoring" / filename
            if not path.exists():
                raise FileNotFoundError(f"Refactoring rule file not found: {path}")
            
            with open(path, 'r', encoding='utf-8') as f:
                rule_content = yaml.safe_load(f)
            
            # Format the YAML rule into a structured prompt for the LLM
            formatted_prompt = "Please refactor the test case by strictly following this YAML rule:\n\n"
            formatted_prompt += "```yaml\n"
            formatted_prompt += yaml.dump(rule_content, allow_unicode=True, sort_keys=False, indent=2)
            formatted_prompt += "```\n\n"
            
            # Add enhanced instructions for DSL strategy with import awareness
            formatted_prompt += """
IMPORTANT INSTRUCTIONS FOR DSL REFACTORING:

1. **Import Requirements**: When using Hamcrest matchers (assertThat, is, not, hasEntry, etc.), you MUST include the necessary imports in your response.

2. **Required Hamcrest Imports**: For any Hamcrest usage with Hamcrest 2.x, include these imports:
   - static org.hamcrest.MatcherAssert.assertThat
   - static org.hamcrest.Matchers.* (or specific matchers like static org.hamcrest.Matchers.is)

3. **JUnit Assumptions**: When replacing assertions with assumptions, use:
   - org.junit.Assume (for JUnit 4)
   - org.junit.jupiter.api.Assumptions (for JUnit 5)

4. **Response Format**: Always provide imports in the "Refactored Test Case Additional Import Packages" section, even if they seem obvious.

5. **Code Quality**: Ensure the refactored code compiles and follows the DSL patterns specified in the YAML rule.

6. **Static Import Format**: When providing imports, use the exact format without 'import ' prefix or ';' suffix:
   - Correct: static org.hamcrest.MatcherAssert.assertThat
   - Correct: static org.hamcrest.Matchers.*
   - Incorrect: import static org.hamcrest.MatcherAssert.assertThat;
"""
            
            return formatted_prompt
        elif "v3-testsmell" in str(self.prompts_dir):
            # For testsmell strategy, use .txt files and different naming convention
            # Convert test smell type to the actual file naming format used in v3-testsmell
            testsmell_mappings = {
                "eager test": "Eager_Test",
                "assertion roulette": "Assertion_Roulette",
                "conditional test logic": "Conditional_Test_Logic",
                "conditional test": "Conditional_Test_Logic",
                "duplicate assert": "Duplicate_Assert", 
                "exception catching throwing": "Exception_Catching_Throwing",
                "exception handling": "Exception_Catching_Throwing",
                "magic number test": "Magic_Number_Test",
                "magic number": "Magic_Number_Test",
                "mystery guest": "Mystery_Guest",
                "print statement": "Print_Statement",
                "redundant print": "Print_Statement",
                "redundant assertion": "Redundant_Assertion",
                "resource optimism": "Resource_Optimism",
                "sensitive equality": "Sensitive_Equality",
                "sleepy test": "Sleepy_Test",
                "verbose test": "Verbose_Test"
            }
            
            normalized_smell = issue_type.lower()
            mapped_filename = testsmell_mappings.get(normalized_smell)
            
            if not mapped_filename:
                # Try exact match with proper case
                mapped_filename = issue_type.replace(" ", "_")
            
            filename = mapped_filename + ".txt"
            path = self.prompts_dir / "refactoring" / filename
            
            if not path.exists():
                raise FileNotFoundError(f"Test smell refactoring prompt not found: {path}")
            
            return path.read_text(encoding='utf-8')
        else:
            # AAA strategy uses .md files
            filename = base_filename + ".md"
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

    def format_refactoring_user_prompt(self, context: TestContext, issue_type: str, test_smell_types: List[str] = None) -> str:
        """Format the user prompt for refactoring."""
        if self.rftype == 'testsmell':
            return self._format_testsmell_refactoring_prompt(context, issue_type, test_smell_types or [])
        else:
            return self._format_aaa_refactoring_prompt(context, issue_type)
    
    def _format_aaa_refactoring_prompt(self, context: TestContext, issue_type: str) -> str:
        """Format the refactoring prompt for AAA and DSL strategies."""
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
    
    def _format_testsmell_refactoring_prompt(self, context: TestContext, issue_type: str, test_smell_types: List[str]) -> str:
        """Format the refactoring prompt for testsmell strategy without AAA information."""
        if not test_smell_types:
            logger.warning(f"No test smell types found for {context.test_class_name}.{context.test_case_name}")
            return ""
        
        # Format test smell types as comma-separated string
        smell_types_str = ', '.join(test_smell_types)
        
        # Load refactoring prompts for each smell type
        refactoring_prompts = []
        for smell_type in test_smell_types:
            try:
                prompt = self.load_refactoring_prompt(smell_type)
                refactoring_prompts.append(f"### Test Smell: {smell_type}\n{prompt}")
            except FileNotFoundError as e:
                logger.warning(f"Refactoring prompt not found for smell type '{smell_type}': {e}")
                continue
        
        if not refactoring_prompts:
            logger.error(f"No refactoring prompts found for any smell types: {test_smell_types}")
            return ""
        
        combined_refactoring_prompt = "\n\n".join(refactoring_prompts)
        if len(refactoring_prompts) > 1:
            combined_refactoring_prompt = "This test case has multiple test smells that need to be addressed:\n\n" + combined_refactoring_prompt + "\n\nPlease refactor the test case to address ALL identified test smells comprehensively."
        
        frameworks = self._analyze_frameworks(context.imported_packages, context.test_case_source_code)
        
        # Create testsmell-specific prompt without AAA information
        return f"""<Test Smell Types>{smell_types_str}</Test Smell Types>
<Test Frameworks>{frameworks}</Test Frameworks>
<Test Case Source Code>{context.test_case_source_code}</Test Case Source Code>
<Test Case Import Packages>{', '.join(context.imported_packages)}</Test Case Import Packages>
<Production Function Implementations>{', '.join(context.production_function_implementations)}</Production Function Implementations>
<Test Case Before Methods>{', '.join(context.before_methods)}</Test Case Before Methods>
<Test Case After Methods>{', '.join(context.after_methods)}</Test Case After Methods>
<Test Case Before All Methods>{', '.join(context.before_all_methods)}</Test Case Before All Methods>
<Test Case After All Methods>{', '.join(context.after_all_methods)}</Test Case After All Methods>
<Refactoring Rules>{combined_refactoring_prompt}</Refactoring Rules>"""
    
    def format_validation_user_prompt(self, context: TestContext, refactored_code: str, all_imports: List[str], original_issue: str, test_smell_types: List[str] = None) -> str:
        """Format the user prompt for validation. Handles multiple issue types."""
        if self.rftype == 'testsmell':
            return self._format_testsmell_validation_prompt(context, refactored_code, all_imports, original_issue, test_smell_types or [])
        else:
            return self._format_aaa_validation_prompt(context, refactored_code, all_imports, original_issue)
    
    def _format_aaa_validation_prompt(self, context: TestContext, refactored_code: str, all_imports: List[str], original_issue: str) -> str:
        """Format the validation prompt for AAA and DSL strategies."""
        # Parse multiple issue types if present
        issue_types = []
        for separator in [',', ';']:
            if separator in original_issue:
                issue_types = [issue.strip().strip('[]') for issue in original_issue.split(separator)]
                break
        
        if not issue_types:
            # Single issue type
            issue_types = [original_issue.strip().strip('[]')]
        
        # Create validation prompt for multiple issues
        if len(issue_types) == 1:
            issues_section = f"<original issue type>{issue_types[0]}</original issue type>"
        else:
            issues_section = f"<original issue types>{', '.join(issue_types)}</original issue types>"
            issues_section += f"\n<individual issue types>"
            for idx, issue in enumerate(issue_types, 1):
                issues_section += f"\n<issue {idx}>{issue}</issue {idx}>"
            issues_section += f"\n</individual issue types>"
        
        return f"""{issues_section}
<Test Case Source Code>{refactored_code}</Test Case Source Code>
<Test Case Import Packages>{', '.join(all_imports)}</Test Case Import Packages>
<Production Function Implementations>{', '.join(context.production_function_implementations)}</Production Function Implementations>
<Test Case Before Methods>{', '.join(context.before_methods)}</Test Case Before Methods>
<Test Case After Methods>{', '.join(context.after_methods)}</Test Case After Methods>
<Test Case Before All Methods>{', '.join(context.before_all_methods)}</Test Case Before All Methods>
<Test Case After All Methods>{', '.join(context.after_all_methods)}</Test Case After All Methods>"""
    
    def _format_testsmell_validation_prompt(self, context: TestContext, refactored_code: str, all_imports: List[str], original_issue: str, test_smell_types: List[str]) -> str:
        """Format the validation prompt for testsmell strategy."""
        if not test_smell_types:
            logger.warning(f"No test smell types found for validation: {context.test_class_name}.{context.test_case_name}")
            # Fallback to original issue if no smell data
            test_smell_types = [original_issue]
        
        # Create validation prompt for multiple test smells
        if len(test_smell_types) == 1:
            smells_section = f"<original smell type>{test_smell_types[0]}</original smell type>"
        else:
            smells_section = f"<original smell types>{', '.join(test_smell_types)}</original smell types>"
            smells_section += f"\n<individual smell types>"
            for idx, smell in enumerate(test_smell_types, 1):
                smells_section += f"\n<smell {idx}>{smell}</smell {idx}>"
            smells_section += f"\n</individual smell types>"
        
        return f"""{smells_section}
<Test Case Source Code>{refactored_code}</Test Case Source Code>
<Test Case Import Packages>{', '.join(all_imports)}</Test Case Import Packages>
<Production Function Implementations>{', '.join(context.production_function_implementations)}</Production Function Implementations>
<Test Case Before Methods>{', '.join(context.before_methods)}</Test Case Before Methods>
<Test Case After Methods>{', '.join(context.after_methods)}</Test Case After Methods>
<Test Case Before All Methods>{', '.join(context.before_all_methods)}</Test Case Before All Methods>
<Test Case After All Methods>{', '.join(context.after_all_methods)}</Test Case After All Methods>"""

class TestRefactor:
    """Main test refactoring orchestrator."""
    
    # Strategy to prompt directory mapping
    STRATEGY_PROMPT_MAPPING = {
        'aaa': 'v1-aaa',
        'dsl': 'v2-dsl-aaa', 
        'testsmell': 'v3-testsmell'
    }
    
    def __init__(self, prompts_dir: Path, data_folder_path: Path, rftype: str, output_path: Path = None, java_project_path: Path = None):
        prompt_subdir = self.STRATEGY_PROMPT_MAPPING.get(rftype, f"v1-{rftype}")
        self.prompt_manager = PromptManager(prompts_dir / prompt_subdir, rftype)
        self.data_folder_path = data_folder_path
        self.llm_client = LLMClient()
        self.sanitizer = Sanitizer()
        self.usage_tracker = UsageTracker(output_path) if output_path else None
        self.rftype = rftype
        
        # Initialize SmartImportManager if java_project_path is provided
        if java_project_path:
            self.import_manager = SmartImportManager(java_project_path)
        else:
            self.import_manager = None
        
        # Load test smell data for testsmell strategy
        self.test_smell_data = {}
        if rftype == 'testsmell':
            self._load_test_smell_data()
    
    def _load_test_smell_data(self):
        """Load test smell data from detailed-smells.csv files in the data folder."""
        logger.info("Loading test smell data for testsmell strategy...")
        
        # Find all *-detailed-smells.csv files in the data folder
        smell_files = list(self.data_folder_path.glob("*-detailed-smells.csv"))
        
        if not smell_files:
            logger.warning("No *-detailed-smells.csv files found in data folder")
            return
        
        for smell_file in smell_files:
            logger.info(f"Loading test smell data from: {smell_file}")
            
            try:
                df = pd.read_csv(smell_file)
                # Expected columns: Absolute Path, Test Class Name, Test Case Name, Test Smell Type
                required_columns = ['Test Class Name', 'Test Case Name', 'Test Smell Type']
                
                if not all(col in df.columns for col in required_columns):
                    logger.warning(f"Skipping {smell_file}: Missing required columns {required_columns}")
                    continue
                
                # Group by test class and method to collect all smell types
                for _, row in df.iterrows():
                    test_class = row['Test Class Name']
                    test_method = row['Test Case Name']
                    smell_type = row['Test Smell Type']
                    
                    if pd.isna(test_class) or pd.isna(test_method) or pd.isna(smell_type):
                        continue
                    
                    key = (test_class, test_method)
                    if key not in self.test_smell_data:
                        self.test_smell_data[key] = []
                    
                    if smell_type not in self.test_smell_data[key]:
                        self.test_smell_data[key].append(smell_type)
                
                logger.info(f"Loaded {len(df)} test smell records from {smell_file.name}")
                
            except Exception as e:
                logger.error(f"Error loading test smell data from {smell_file}: {e}")
        
        logger.info(f"Total test cases with smell data: {len(self.test_smell_data)}")
    
    def _get_test_smell_types(self, test_class: str, test_method: str) -> List[str]:
        """Get test smell types for a specific test case."""
        key = (test_class, test_method)
        return self.test_smell_data.get(key, [])

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
        
        # Enhanced import detection for DSL strategy
        if self.rftype == 'dsl' and self.import_manager and refactored_code:
            auto_detected_imports = self._detect_missing_imports_for_dsl(refactored_code, result["additional_imports"])
            if auto_detected_imports:
                logger.info(f"Auto-detected {len(auto_detected_imports)} missing imports for DSL strategy")
                result["additional_imports"].extend(auto_detected_imports)
        
        return result
    
    def _detect_missing_imports_for_dsl(self, code: str, existing_imports: List[str]) -> List[str]:
        """Detect missing imports specifically for DSL refactored code."""
        if not self.import_manager:
            return []
        
        # Convert existing imports to set for faster lookup
        existing_set = set(existing_imports)
        
        # Use SmartImportManager to analyze the code
        requirements = self.import_manager.analyze_code_requirements(code, existing_set)
        
        # Convert requirements to import statements
        missing_imports = []
        for req in requirements:
            import_stmt = req.import_statement
            if not import_stmt.startswith('import '):
                import_stmt = f"import {import_stmt};"
            
            # Remove 'import ' and ';' for consistency with our format
            clean_import = import_stmt.replace('import ', '').replace(';', '').strip()
            
            if clean_import not in existing_set:
                missing_imports.append(clean_import)
                logger.debug(f"Auto-detected missing import: {clean_import} ({req.reason})")
        
        return missing_imports
    
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
        """Parse LLM validation response with robust parsing. Handles multiple issue types and test smells."""
        result = {
            "original_issue_exists": True,
            "new_issue_exists": False,
            "new_issue_type": "",
            "reasoning": "",
            "individual_issue_status": []  # For tracking multiple issues
        }
        
        # Determine if this is testsmell validation based on response content
        is_testsmell = self.rftype == 'testsmell' or 'smell' in response.lower()
        
        if is_testsmell:
            # For testsmell validation, look for smell-specific tags
            individual_smells = []
            smell_count = 1
            while True:
                smell_exists_text = self._extract_xml_content(response, f"smell {smell_count} exists")
                if not smell_exists_text:
                    break
                individual_smells.append({
                    "issue_number": smell_count,
                    "exists": self._parse_boolean(smell_exists_text)
                })
                smell_count += 1
            
            if individual_smells:
                # Multiple smells case
                result["individual_issue_status"] = individual_smells
                result["original_issue_exists"] = any(smell["exists"] for smell in individual_smells)
            else:
                # Single smell case
                original_exists_text = self._extract_xml_content(response, "original smell type exists")
                if original_exists_text:
                    result["original_issue_exists"] = self._parse_boolean(original_exists_text)
                
                # Also try plural format
                original_exists_plural = self._extract_xml_content(response, "original smell types exist")
                if original_exists_plural:
                    result["original_issue_exists"] = self._parse_boolean(original_exists_plural)
            
            # Extract new smell existence
            new_exists_text = self._extract_xml_content(response, "new smell type exists")
            if new_exists_text:
                result["new_issue_exists"] = self._parse_boolean(new_exists_text)
            
            # Extract new smell type
            new_smell_type = self._extract_xml_content(response, "new smell type")
            if new_smell_type:
                result["new_issue_type"] = new_smell_type
        else:
            # Original AAA/DSL validation logic
            individual_issues = []
            issue_count = 1
            while True:
                issue_exists_text = self._extract_xml_content(response, f"issue {issue_count} exists")
                if not issue_exists_text:
                    break
                individual_issues.append({
                    "issue_number": issue_count,
                    "exists": self._parse_boolean(issue_exists_text)
                })
                issue_count += 1
            
            if individual_issues:
                # Multiple issues case
                result["individual_issue_status"] = individual_issues
                result["original_issue_exists"] = any(issue["exists"] for issue in individual_issues)
            else:
                # Single issue case - try legacy format
                original_exists_text = self._extract_xml_content(response, "original issue type exists")
                if original_exists_text:
                    result["original_issue_exists"] = self._parse_boolean(original_exists_text)
                
                # Also try plural format for backward compatibility
                original_exists_plural = self._extract_xml_content(response, "original issue types exist")
                if original_exists_plural:
                    result["original_issue_exists"] = self._parse_boolean(original_exists_plural)
            
            # Extract new issue existence
            new_exists_text = self._extract_xml_content(response, "new issue type exists")
            if new_exists_text:
                result["new_issue_exists"] = self._parse_boolean(new_exists_text)
            
            # Extract new issue type
            new_issue_type = self._extract_xml_content(response, "new issue type")
            if new_issue_type:
                result["new_issue_type"] = new_issue_type
        
        # Extract reasoning (common for both)
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
    
    def refactor_test_case(self, test_case: TestCase, rftype: str = "", debug_mode: bool = False, max_refinement_loops: int = 5) -> RefactoringResult:
        """
        Refactors a single test case using a two-loop process.
        - Outer loop: Validation-driven refinement (max 5 iterations).
        - Inner loop: Code sanitization to get a clean response (max 3 retries).
        """
        start_time = time.time()
        usage_start_time = self.usage_tracker.start_timing() if self.usage_tracker else start_time
        
        try:
            context = self.load_test_context(
                test_case.project_name,
                test_case.test_class_name,
                test_case.test_method_name
            )
            
            # For testsmell strategy, check if we have test smell data for this test case
            if self.rftype == 'testsmell':
                test_smell_types = self._get_test_smell_types(context.test_class_name, context.test_case_name)
                if not test_smell_types:
                    logger.info(f"No test smells found for {context.test_class_name}.{context.test_case_name}, skipping refactoring")
                    return RefactoringResult(
                        success=True,
                        refactored_code=context.test_case_source_code,  # Return original code
                        error_message="Skipped: No test smells found",
                        iterations=0,
                        processing_time=time.time() - start_time
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
                    
                    # For testsmell strategy, get test smell types and pass them to the prompt manager
                    if self.rftype == 'testsmell':
                        test_smell_types = self._get_test_smell_types(context.test_class_name, context.test_case_name)
                        user_prompt = self.prompt_manager.format_refactoring_user_prompt(context, test_case.issue_type, test_smell_types)
                    else:
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
                    error_msg = f"Failed to get a clean response from LLM after {max_sanitizer_retries} attempts."
                    usage_stats = self.llm_client.get_usage_stats()
                    
                    # Record usage statistics for sanitizer failure
                    if self.usage_tracker:
                        self.usage_tracker.record_usage(
                            project=test_case.project_name,
                            test_class=test_case.test_class_name,
                            test_case=test_case.test_method_name,
                            cost=usage_stats["total_cost"],
                            start_time=usage_start_time,
                            refactoring_loops=loop_num + 1,
                            strategy=rftype,
                            tokens_used=usage_stats["total_tokens"],
                            success=False,
                            error_message=error_msg
                        )
                    
                    return RefactoringResult(
                        success=False, error_message=error_msg,
                        iterations=loop_num + 1, processing_time=time.time() - start_time,
                        tokens_used=usage_stats["total_tokens"], cost=usage_stats["total_cost"]
                    )
                
                # --- End of inner sanitizer loop. We now have good, sanitized code. ---
                logger.debug(f"\n--- Sanitized Code (Loop {loop_num+1}) ---\n{sanitized_code}\n---")
                
                # 4. Validate the sanitized code
                all_imports = context.imported_packages + parsed_llm_result.get("additional_imports", [])
                if self.rftype == 'testsmell':
                    test_smell_types = self._get_test_smell_types(context.test_class_name, context.test_case_name)
                    validation_prompt = self.prompt_manager.format_validation_user_prompt(context, sanitized_code, all_imports, test_case.issue_type, test_smell_types)
                else:
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
                    
                    # Record usage statistics
                    if self.usage_tracker:
                        self.usage_tracker.record_usage(
                            project=test_case.project_name,
                            test_class=test_case.test_class_name,
                            test_case=test_case.test_method_name,
                            cost=usage_stats["total_cost"],
                            start_time=usage_start_time,
                            refactoring_loops=loop_num + 1,
                            strategy=rftype,
                            tokens_used=usage_stats["total_tokens"],
                            success=True
                        )
                    
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
            error_msg = f"Maximum refinement loops ({max_refinement_loops}) reached without success."
            
            # Record usage statistics for failure
            if self.usage_tracker:
                self.usage_tracker.record_usage(
                    project=test_case.project_name,
                    test_class=test_case.test_class_name,
                    test_case=test_case.test_method_name,
                    cost=usage_stats["total_cost"],
                    start_time=usage_start_time,
                    refactoring_loops=max_refinement_loops,
                    strategy=rftype,
                    tokens_used=usage_stats["total_tokens"],
                    success=False,
                    error_message=error_msg
                )
            
            return RefactoringResult(
                success=False, error_message=error_msg,
                iterations=max_refinement_loops, chat_history=json.dumps(refactoring_session_messages, indent=2),
                tokens_used=usage_stats["total_tokens"], cost=usage_stats["total_cost"],
                processing_time=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"  ✗ An unexpected error occurred during refactoring: {e}", exc_info=debug_mode)
            usage_stats = self.llm_client.get_usage_stats()
            error_msg = str(e)
            
            # Record usage statistics for exception
            if self.usage_tracker:
                self.usage_tracker.record_usage(
                    project=test_case.project_name,
                    test_class=test_case.test_class_name,
                    test_case=test_case.test_method_name,
                    cost=usage_stats["total_cost"],
                    start_time=usage_start_time,
                    refactoring_loops=0,
                    strategy=rftype,
                    tokens_used=usage_stats["total_tokens"],
                    success=False,
                    error_message=error_msg
                )
            
            return RefactoringResult(
                success=False, error_message=error_msg,
                iterations=0, # Or pass loop_num if you can
                tokens_used=usage_stats["total_tokens"], cost=usage_stats["total_cost"],
                processing_time=time.time() - start_time
            )