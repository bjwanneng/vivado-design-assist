"""
配置管理模块

使用 Pydantic Settings 管理应用配置，支持从：
1. 环境变量（VMC_LLM_*）
2. .env 文件（当前目录）
3. ~/.config/vmc/settings.json（用户配置文件）
4. ~/.vmc.env（用户环境文件）
"""

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM 配置"""
    model_config = SettingsConfigDict(env_prefix="VMC_LLM_")

    provider: str = Field(default="claude", description="LLM 提供者: claude, openai, local")
    model: str = Field(default="claude-sonnet-4-20250514", description="模型名称")
    api_key: Optional[str] = Field(default=None, description="API Key")
    base_url: Optional[str] = Field(default=None, description="自定义 API 基础 URL")
    max_tokens: int = Field(default=2048, description="最大 Token 数")
    temperature: float = Field(default=0.3, description="温度参数")


class AppConfig(BaseSettings):
    """VMC 应用主配置"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enable_ai: bool = Field(default=True, description="启用 AI 解读")
    llm: LLMSettings = Field(default_factory=LLMSettings)


def _get_config_dir() -> Path:
    """获取配置目录

    支持多种运行场景：
    1. 开发环境：当前工作目录下的 .vmc/
    2. 打包后（可写目录）：同上
    3. 打包后（只读目录，如 /usr/bin）：用户数据目录
       - Linux: ~/.local/share/vmc/
       - macOS: ~/Library/Application Support/vmc/
       - Windows: %APPDATA%/vmc/
    4. 环境变量覆盖：VMC_CONFIG_DIR
    """
    # 环境变量优先级最高
    env_dir = os.environ.get("VMC_CONFIG_DIR")
    if env_dir:
        p = Path(env_dir)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except OSError:
            pass

    # 尝试当前工作目录（开发模式或便携模式）
    cwd_vmc = Path.cwd() / ".vmc"
    try:
        # 测试是否可写
        cwd_vmc.mkdir(parents=True, exist_ok=True)
        test_file = cwd_vmc / ".write_test"
        test_file.write_text("1")
        test_file.unlink()
        return cwd_vmc
    except OSError:
        pass

    # 回退到平台相关的用户数据目录
    home = Path.home()
    system = os.name  # 'nt' for Windows, 'posix' for Linux/macOS

    if system == "nt":
        # Windows: %APPDATA%/vmc
        appdata = os.environ.get("APPDATA")
        if appdata:
            p = Path(appdata) / "vmc"
        else:
            p = home / "AppData" / "Roaming" / "vmc"
    else:
        # Linux/macOS
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            p = Path(xdg_data) / "vmc"
        elif (home / ".local" / "share").exists():
            p = home / ".local" / "share" / "vmc"
        else:
            # macOS fallback
            p = home / "Library" / "Application Support" / "vmc"

    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def _get_user_config_path() -> Path:
    """获取用户配置文件路径"""
    return _get_config_dir() / "settings.json"


def _load_user_config() -> dict:
    """从用户配置文件加载"""
    config_path = _get_user_config_path()
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_user_config(data: dict) -> None:
    """保存到用户配置文件"""
    config_path = _get_user_config_path()
    try:
        config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _get_user_env_path() -> Path:
    """获取用户环境文件路径"""
    return Path.home() / ".vmc.env"


def _load_user_env() -> dict:
    """从 ~/.vmc.env 加载"""
    env_path = _get_user_env_path()
    if not env_path.exists():
        return {}
    result = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip('"\'')
    return result


_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置实例（单例模式）

    优先级（高到低）：
    1. 环境变量（VMC_LLM_*）
    2. ~/.vmc.env
    3. ~/.config/vmc/settings.json
    4. 当前目录 .env
    5. 默认值
    """
    global _config
    if _config is None:
        # 从用户配置文件加载
        user_config = _load_user_config()
        user_env = _load_user_env()

        # 合并配置（环境变量优先级最高，已在 pydantic 中处理）
        # 先设置用户配置文件中的值到环境变量
        for key, value in user_env.items():
            if key.startswith("VMC_") and key not in os.environ:
                os.environ[key] = value

        _config = AppConfig(**user_config)
    return _config


def update_llm_config(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> None:
    """更新 LLM 配置并保存到用户配置文件"""
    global _config
    cfg = get_config()

    if provider is not None:
        cfg.llm.provider = provider
    if model is not None:
        cfg.llm.model = model
    if api_key is not None:
        cfg.llm.api_key = api_key
    if base_url is not None:
        cfg.llm.base_url = base_url
    if max_tokens is not None:
        cfg.llm.max_tokens = max_tokens
    if temperature is not None:
        cfg.llm.temperature = temperature

    # 保存到用户配置文件
    data = {
        "llm": {
            "provider": cfg.llm.provider,
            "model": cfg.llm.model,
            "api_key": cfg.llm.api_key,
            "base_url": cfg.llm.base_url,
            "max_tokens": cfg.llm.max_tokens,
            "temperature": cfg.llm.temperature,
        }
    }
    _save_user_config(data)

    # 同步更新环境变量（供子进程使用）
    os.environ["VMC_LLM_PROVIDER"] = cfg.llm.provider
    os.environ["VMC_LLM_MODEL"] = cfg.llm.model
    if cfg.llm.api_key:
        os.environ["VMC_LLM_API_KEY"] = cfg.llm.api_key
    if cfg.llm.base_url:
        os.environ["VMC_LLM_BASE_URL"] = cfg.llm.base_url
    os.environ["VMC_LLM_MAX_TOKENS"] = str(cfg.llm.max_tokens)
    os.environ["VMC_LLM_TEMPERATURE"] = str(cfg.llm.temperature)


def get_llm_config_dict() -> dict:
    """获取 LLM 配置字典（用于 API 返回）"""
    cfg = get_config()
    return {
        "provider": cfg.llm.provider,
        "model": cfg.llm.model,
        "base_url": cfg.llm.base_url,
        "max_tokens": cfg.llm.max_tokens,
        "temperature": cfg.llm.temperature,
        # api_key 不返回完整值，只返回是否已设置
        "has_api_key": cfg.llm.api_key is not None and len(cfg.llm.api_key) > 0,
    }
