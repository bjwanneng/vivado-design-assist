"""Claude API Provider"""

import os
from typing import Generator, Optional, List

from vivado_ai.core.llm_provider import LLMProvider, LLMConfig, LLMResponse, ToolCall


class ClaudeProvider(LLMProvider):
    """Claude (Anthropic) API 提供者"""

    def _setup_client(self) -> None:
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self._client = anthropic.Anthropic(
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
            response = self._client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            # 安全提取文本（兼容 ThinkingBlock 等无 text 属性的块）
            text_content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text_content = block.text
                    break

            return LLMResponse(
                text=text_content,
                usage={
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                },
            )
        except Exception as e:
            raise RuntimeError(f"Claude API error: {e}") from e

    def chat_stream(
        self,
        system_prompt: str,
        user_message: str,
    ) -> Generator[str, None, None]:
        try:
            with self._client.messages.stream(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            raise RuntimeError(f"Claude stream error: {e}") from e
