#!/usr/bin/env python3
"""Unit tests for LLM client module."""

import unittest
from unittest.mock import patch, MagicMock
import os

from src.llm_client import LLMClient


class TestLLMClient(unittest.TestCase):
    """Test the LLMClient class."""
    
    def setUp(self):
        """Set up test environment."""
        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            'OPENAI_API_KEY': 'test-api-key',
            'OPENAI_MODEL': 'test-model',
            'OPENAI_REASONING_EFFORT': 'low',
            'OPENAI_MAX_TOKENS': '2048'
        })
        self.env_patcher.start()
    
    def tearDown(self):
        """Clean up test environment."""
        self.env_patcher.stop()
    
    @patch('src.llm_client.OpenAI')
    def test_llm_client_initialization(self, mock_openai):
        """Test LLM client initialization."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        client = LLMClient()
        
        self.assertEqual(client.model, 'test-model')
        self.assertEqual(client.reasoning_effort, 'low')
        self.assertEqual(client.max_tokens, 2048)
        self.assertEqual(client.total_tokens_used, 0)
        self.assertEqual(client.total_cost, 0.0)
        mock_openai.assert_called_once_with(api_key='test-api-key')
    
    @patch('src.llm_client.OpenAI')
    def test_create_chat_completion_success(self, mock_openai):
        """Test successful chat completion."""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.usage.total_tokens = 100
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        client = LLMClient()
        messages = [{"role": "user", "content": "Test message"}]
        
        result = client.create_chat_completion(messages)
        
        self.assertEqual(result, "Test response")
        self.assertEqual(client.total_tokens_used, 100)
        self.assertGreater(client.total_cost, 0)
        
        mock_client.chat.completions.create.assert_called_once_with(
            model='test-model',
            messages=messages,
            response_format={"type": "text"},
            reasoning_effort='low',
            max_tokens=2048
        )
    
    @patch('src.llm_client.OpenAI')
    def test_create_chat_completion_failure(self, mock_openai):
        """Test chat completion failure."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client
        
        client = LLMClient()
        messages = [{"role": "user", "content": "Test message"}]
        
        with self.assertRaises(Exception) as context:
            client.create_chat_completion(messages)
        
        self.assertIn("LLM API call failed", str(context.exception))
    
    @patch('src.llm_client.OpenAI')
    def test_refactor_test_case(self, mock_openai):
        """Test refactor test case method."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Refactored code"
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        client = LLMClient()
        system_prompt = "You are a refactoring assistant"
        user_prompt = "Refactor this test"
        
        result = client.refactor_test_case(system_prompt, user_prompt)
        
        self.assertEqual(result, "Refactored code")
        mock_client.chat.completions.create.assert_called_once()
        
        # Check that correct messages were passed
        call_args = mock_client.chat.completions.create.call_args[1]
        messages = call_args['messages']
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertEqual(messages[0]['content'], system_prompt)
        self.assertEqual(messages[1]['role'], 'user')
        self.assertEqual(messages[1]['content'], user_prompt)
    
    @patch('src.llm_client.OpenAI')
    def test_validate_refactored_code(self, mock_openai):
        """Test validate refactored code method."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Validation result"
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        client = LLMClient()
        system_prompt = "You are a validation assistant"
        user_prompt = "Validate this code"
        
        result = client.validate_refactored_code(system_prompt, user_prompt)
        
        self.assertEqual(result, "Validation result")
    
    @patch('src.llm_client.OpenAI')
    def test_get_usage_stats(self, mock_openai):
        """Test getting usage statistics."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        client = LLMClient()
        client.total_tokens_used = 500
        client.total_cost = 0.05
        
        stats = client.get_usage_stats()
        
        self.assertEqual(stats['total_tokens'], 500)
        self.assertEqual(stats['total_cost'], 0.05)
    
    @patch('src.llm_client.OpenAI')
    def test_default_environment_values(self, mock_openai):
        """Test default environment values when not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ['OPENAI_API_KEY'] = 'test-key'
            
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            
            client = LLMClient()
            
            self.assertEqual(client.model, 'o4-mini')  # Default value
            self.assertEqual(client.reasoning_effort, 'medium')  # Default value
            self.assertEqual(client.max_tokens, 4096)  # Default value


if __name__ == '__main__':
    unittest.main()