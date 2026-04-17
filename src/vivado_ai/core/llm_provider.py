"""
LLM Provider 模块

提供统一的 LLM 调用接口，支持多种模型后端：
- Claude (Anthropic) - 主力模型
- OpenAI (GPT) - 备用/可选
- 本地模型 (Ollama/vLLM) - 离线/私有化部署
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable, Generator, Any, Union, AsyncGenerator
from enum import Enum
import json
import time
import asyncio
from contextlib import asynccontextmanager


class LLMError(Exception):
    """LLM 调用错误基类"""
    pass


class LLMRateLimitError(LLMError):
    """速率限制错误"""
    pass


class LLMTimeoutError(LLMError):
    """超时错误"""
    pass


class LLMProviderType(Enum):
    """LLM 提供者类型"""
    CLAUDE = "claude"
    OPENAI = "openai"
    LOCAL = "local"


@dataclass
class LLMConfig:
    """
    LLM 配置

    Attributes:
        provider: 提供者类型 (claude / openai / local)
        model: 模型名称
        api_key: API Key
        base_url: 自定义 API 基础 URL
        max_tokens: 最大 Token 数
        temperature: 温度参数 (0-2)
        top_p: Top-p 采样参数
        timeout: 请求超时时间（秒）
        retry_count: 重试次数
        retry_delay: 重试延迟（秒）
    """
    provider: str = "claude"
    model: str = "claude-sonnet-4-20250514"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.3
    top_p: float = 0.9
    timeout: int = 60
    retry_count: int = 3
    retry_delay: float = 1.0

    def __post_init__(self):
        """验证配置"""
        valid_providers = ["claude", "openai", "local"]
        if self.provider not in valid_providers:
            raise ValueError(f"Invalid provider: {self.provider}. Must be one of {valid_providers}")

        if not 0 <= self.temperature <= 2:
            raise ValueError(f"temperature must be between 0 and 2, got {self.temperature}")


@dataclass
class LLMResponse:
    """
    LLM 响应

    Attributes:
        text: 响应文本
        usage: Token 使用情况
        model: 使用的模型名称
        finish_reason: 结束原因
        latency: 延迟（秒）
        metadata: 额外元数据
    """
    text: str
    usage: Dict[str, int] = field(default_factory=dict)
    model: str = ""
    finish_reason: str = ""
    latency: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """确保 usage 有默认值"""
        if not self.usage:
            self.usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }

    @property
    def total_tokens(self) -> int:
        """总 Token 数"""
        return self.usage.get("total_tokens", 0)

    @property
    def prompt_tokens(self) -> int:
        """提示 Token 数"""
        return self.usage.get("prompt_tokens", 0)

    @property
    def completion_tokens(self) -> int:
        """完成 Token 数"""
        return self.usage.get("completion_tokens", 0)


@dataclass
class ToolCall:
    """工具调用定义"""
    name: str
    description: str
    parameters: Dict[str, Any]


class LLMProvider(ABC):
    """
    LLM 提供者基类

    所有 LLM 提供者的抽象基类，定义了统一的接口。
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
        self._setup_client()

    @abstractmethod
    def _setup_client(self) -> None:
        """设置客户端（由子类实现）"""
        pass

    @abstractmethod
    def chat(
        self,
        system_prompt: str,
        user_message: str,
        tools: Optional[List[ToolCall]] = None,
    ) -> LLMResponse:
        """
        发送对话请求（同步）

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息
            tools: 可用工具列表

        Returns:
            LLMResponse: 响应结果
        """
        pass

    @abstractmethod
    def chat_stream(
        self,
        system_prompt: str,
        user_message: str,
    ) -> Generator[str, None, None]:
        """
        发送对话请求（流式）

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息

        Yields:
            str: 响应文本片段
        """
        pass

    def health_check(self) -> bool:
        """
        健康检查

        Returns:
            bool: 是否健康
        """
        try:
            response = self.chat(
                "You are a helpful assistant.",
                "Return 'OK' if you can hear me.",
            )
            return "OK" in response.text or len(response.text) > 0
        except Exception as e:
            self._log_error(f"Health check failed: {e}")
            return False

    def _retry_with_backoff(self, func, *args, **kwargs):
        """
        带指数退避的重试

        Args:
            func: 要执行的函数
            *args, **kwargs: 函数参数

        Returns:
            函数返回值

        Raises:
            LLMError: 重试耗尽后抛出
        """
        for attempt in range(self.config.retry_count):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt < self.config.retry_count - 1:
                    delay = self.config.retry_delay * (2 ** attempt)
                    self._log_warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    raise LLMError(f"Failed after {self.config.retry_count} attempts: {e}") from e

    def _log_info(self, message: str) -> None:
        """记录信息日志"""
        print(f"[INFO] {message}")

    def _log_warning(self, message: str) -> None:
        """记录警告日志"""
        print(f"[WARNING] {message}")

    def _log_error(self, message: str) -> None:
        """记录错误日志"""
        print(f"[ERROR] {message}")


# 工具函数
def create_llm(config: LLMConfig) -> LLMProvider:
    """
    创建 LLM 提供者

    Args:
        config: LLM 配置

    Returns:
        LLMProvider: LLM 提供者实例

    Raises:
        ValueError: 未知的提供者类型
    """
    from .claude_provider import ClaudeProvider
    from .openai_provider import OpenAIProvider
    from .local_provider import LocalProvider

    providers = {
        "claude": ClaudeProvider,
        "openai": OpenAIProvider,
        "local": LocalProvider,
    }

    provider_class = providers.get(config.provider)
    if not provider_class:
        raise ValueError(f"Unknown provider: {config.provider}")

    return provider_class(config)


def get_recommended_model(provider: str, task_type: str) -> str:
    """
    根据任务类型推荐模型

    Args:
        provider: 提供者类型
        task_type: 任务类型

    Returns:
        str: 推荐的模型名称
    """
    recommendations = {
        "claude": {
            "report_analysis": "claude-sonnet-4-20250514",
            "constraint_gen": "claude-sonnet-4-20250514",
            "strategy_recommend": "claude-sonnet-4-20250514",
            "chat": "claude-haiku-4-20250514",
            "complex_reasoning": "claude-opus-4-20250514",
        },
        "openai": {
            "report_analysis": "gpt-4o",
            "constraint_gen": "gpt-4o",
            "strategy_recommend": "gpt-4o",
            "chat": "gpt-4o-mini",
            "complex_reasoning": "gpt-4o",
        },
        "local": {
            "report_analysis": "qwen2.5:72b",
            "constraint_gen": "qwen2.5:32b",
            "strategy_recommend": "qwen2.5:72b",
            "chat": "qwen2.5:14b",
            "complex_reasoning": "qwen2.5:72b",
        },
    }

    return recommendations.get(provider, {}).get(task_type, "claude-sonnet-4-20250514")
