import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel

class GeminiClient:
    def __init__(self):
        # The SDK automatically picks up GEMINI_API_KEY from the environment
        self.client = genai.Client()
        self.model_id = "gemini-3.1-flash-lite"

    def generate_text(self, prompt: str) -> str:
        """Generates raw text for the Creator and Editor agents."""
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=prompt,
        )
        return response.text

    def generate_json(self, prompt: str, response_model: type[BaseModel]) -> str:
        """
        Forces the LLM to return structured JSON adhering to the Pydantic model.
        Used by the Evaluator agent.
        """
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_model,
            ),
        )
        # We return the JSON string so brain_service.py can parse it
        return response.text