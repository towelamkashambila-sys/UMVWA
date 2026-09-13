from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class AIResult:
    status: str
    answer: str | None = None
    provider: str | None = None
    grounded: bool = False
    error: str | None = None

class OperationalAIProvider(Protocol):
    def answer(self, *, question: str, grounded_sources: list[dict], role: str) -> AIResult: ...

class DisabledAIProvider:
    """Safe default: never invents an answer when no production model is configured."""
    def answer(self, *, question: str, grounded_sources: list[dict], role: str) -> AIResult:
        return AIResult(status='NOT_CONFIGURED', provider=None, grounded=bool(grounded_sources))

def ai_status() -> dict:
    provider = 'disabled'
    if __import__('os').environ.get('UMVWA_AI_PROVIDER'):
        provider = __import__('os').environ['UMVWA_AI_PROVIDER']
    return {'configured': provider != 'disabled', 'provider': provider, 'human_control': True}
