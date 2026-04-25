"""OpenAI API Provider"""

import os
from typing import Generator, Optional, List

from vivado_ai.core.llm_provider import LLMProvider, LLMConfig, LLMResponse, ToolCall


class OpenAIProvider(LLMProvider):
    """OpenAI API 提供者"""

    def _setup_client(self) -> None:
        try:
            import openai
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

        api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=self.config.base_url,
        )

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        tools: Optional[List[ToolCall]] = None,
    ) -> LLMResponse:
        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            return LLMResponse(
                text=response.choices[0].message.content or "",
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}") from e

    def chat_stream(
        self,
        system_prompt: str,
        user_message: str,
    ) -> Generator[str, None, None]:
        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                stream=True,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise RuntimeError(f"OpenAI stream error: {e}") from e
