"""
配置管理模块

使用 Pydantic Settings 管理应用配置，支持从环境变量、.env 文件加载。
v2.0 简化版：移除 Database/Cache/API 配置（不再需要）。
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM 配置"""
    model_config = SettingsConfigDict(env_prefix="VMC_LLM_")

    provider: str = Field(default="claude", description="LLM 提供者: claude, openai")
    model: str = Field(default="claude-haiku-4-20250514", description="模型名称")
    api_key: Optional[str] = Field(default=None, description="API Key")
    base_url: Optional[str] = Field(default=None, description="自定义 API 基础 URL")
    max_tokens: int = Field(default=512, description="最大 Token 数")
    temperature: float = Field(default=0.2, description="温度参数")


class AppConfig(BaseSettings):
    """VMC 应用主配置"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    enable_ai: bool = Field(default=True, description="启用 AI 解读")
    llm: LLMSettings = Field(default_factory=LLMSettings)


_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置实例（单例模式）"""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config
