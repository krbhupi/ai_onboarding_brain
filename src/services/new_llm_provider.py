"""New LLM provider for gpt-oss-20b model."""
import json
import httpx
from typing import List, Dict, Any, Optional
from config.logging import logger


class NewLLMProvider:
    """LLM provider for gpt-oss-20b model at http://172.17.58.114:8002/v1/chat/completions."""

    def __init__(self, model: str = "gpt-oss-20b",
                 url: str = "http://172.17.58.114:8002/v1/chat/completions"):
        self.model = model
        self.url = url
        self.headers = {"Content-Type": "application/json"}

    async def invoke(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        """
        Send messages to the LLM API and return the response text.

        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            temperature: Sampling temperature for generation (default: 0.7)

        Returns:
            Response text from the LLM

        Raises:
            httpx.HTTPError: If the API request fails
            Exception: For other errors
        """
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature
            }

            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(self.url, headers=self.headers, json=payload)
                response.raise_for_status()
                data = response.json()

                # Extract response content - adjust based on actual API response format
                return data["choices"][0]["message"]["content"]

        except httpx.HTTPError as e:
            logger.error(f"New LLM API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in New LLM provider: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if the LLM service is available."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self.url.replace("/chat/completions", "/models"))
                return response.status_code == 200
        except Exception as e:
            logger.error(f"New LLM health check failed: {e}")
            return False