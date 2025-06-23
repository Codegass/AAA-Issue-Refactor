"""LLM client for interacting with OpenAI API."""

import os
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

class LLMClient:
    """Client for OpenAI API interactions."""
    
    def __init__(self):
        load_dotenv()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "o4-mini")
        self.reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "medium")
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "20000"))
        self.total_tokens_used = 0
        self.total_cost = 0.0
        
        # o4-mini pricing (per 1M tokens)
        self.input_cost_per_token = 1.100 / 1_000_000  # $1.100 per 1M input tokens
        self.cached_input_cost_per_token = 0.275 / 1_000_000  # $0.275 per 1M cached input tokens
        self.output_cost_per_token = 4.400 / 1_000_000  # $4.400 per 1M output tokens
    
    def create_chat_completion(self, messages: list, response_format: Optional[Dict[str, Any]] = None) -> str:
        """Create a chat completion using OpenAI API."""
        try:
            # Use the correct parameter name based on model
            completion_params = {
                "model": self.model,
                "messages": messages,
                "response_format": response_format or {"type": "text"},
                "reasoning_effort": self.reasoning_effort,
            }
            
            # Use max_completion_tokens for o4 models, max_tokens for others
            if "o4" in self.model.lower():
                completion_params["max_completion_tokens"] = self.max_tokens
            else:
                completion_params["max_tokens"] = self.max_tokens
            
            response = self.client.chat.completions.create(**completion_params)
            
            # Track usage with accurate o4-mini pricing
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                self.total_tokens_used += usage.total_tokens
                
                # Calculate cost based on o4-mini pricing
                input_tokens = usage.prompt_tokens
                output_tokens = usage.completion_tokens
                
                # Try to get cached tokens if available (newer API versions)
                cached_tokens = 0
                if hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
                    if hasattr(usage.prompt_tokens_details, 'cached_tokens'):
                        cached_tokens = usage.prompt_tokens_details.cached_tokens
                
                # Adjust input tokens for cached tokens
                regular_input_tokens = input_tokens - cached_tokens
                
                cost = (regular_input_tokens * self.input_cost_per_token + 
                       cached_tokens * self.cached_input_cost_per_token +
                       output_tokens * self.output_cost_per_token)
                       
                self.total_cost += cost
            
            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"LLM API call failed: {str(e)}")
    
    def send_chat_request(self, system_prompt: str, messages: list) -> str:
        """Send a chat request with system prompt and message history."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        return self.create_chat_completion(full_messages)
    
    def refactor_test_case(self, system_prompt: str, user_prompt: str) -> str:
        """Perform test case refactoring using LLM."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        return self.create_chat_completion(messages)
    
    def validate_refactored_code(self, system_prompt: str, user_prompt: str) -> str:
        """Validate refactored code using LLM."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        return self.create_chat_completion(messages)
    
    def reset_usage_stats(self):
        """Reset usage statistics to zero."""
        self.total_tokens_used = 0
        self.total_cost = 0.0
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current usage statistics."""
        return {
            "total_tokens": self.total_tokens_used,
            "total_cost": self.total_cost
        }