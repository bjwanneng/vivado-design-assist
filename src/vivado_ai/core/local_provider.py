"""Local LLM Provider (Ollama / vLLM)"""

from typing import Generator, Optional, List

from vivado_ai.core.llm_provider import LLMProvider, LLMConfig, LLMResponse, ToolCall


class LocalProvider(LLMProvider):
    """本地模型提供者（Ollama / vLLM）"""

    def _setup_client(self) -> None:
        try:
            import openai
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

        base_url = self.config.base_url or "http://localhost:11434/v1"
        self._client = openai.OpenAI(
            api_key="ollama",  # Ollama 不需要真实 key
            base_url=base_url,
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
            raise RuntimeError(f"Local LLM error: {e}") from e

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
            raise RuntimeError(f"Local LLM stream error: {e}") from e
