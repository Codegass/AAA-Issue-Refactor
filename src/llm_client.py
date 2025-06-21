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
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "4096"))
        self.total_tokens_used = 0
        self.total_cost = 0.0
    
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
            
            # Track usage
            if hasattr(response, 'usage') and response.usage:
                self.total_tokens_used += response.usage.total_tokens
                # Rough cost calculation (adjust based on actual pricing)
                self.total_cost += response.usage.total_tokens * 0.0001
            
            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"LLM API call failed: {str(e)}")
    
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
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current usage statistics."""
        return {
            "total_tokens": self.total_tokens_used,
            "total_cost": self.total_cost
        }