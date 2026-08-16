"""LLM Provider 统一接口。后续可增加 OpenAIProvider / ClaudeProvider / QwenProvider。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 60.0,
    ) -> str: ...

    @abstractmethod
    def available(self) -> bool:
        """是否配置可用（API Key 已配置）。"""
        ...


class LLMUnavailableError(RuntimeError):
    """LLM 未配置或调用失败。上层必须降级处理，不影响软件其他功能。"""
