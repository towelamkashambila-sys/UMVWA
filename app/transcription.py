from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class TranscriptionResult:
    status: str
    transcript: str | None = None
    provider: str | None = None
    error: str | None = None

class TranscriptionProvider(Protocol):
    def transcribe(self, audio_path: str, content_type: str) -> TranscriptionResult: ...

class PendingTranscriptionProvider:
    """Explicit production seam: never fabricates a transcript."""
    def transcribe(self, audio_path: str, content_type: str) -> TranscriptionResult:
        return TranscriptionResult(status="PENDING_PROVIDER", provider=None)

def transcribe(audio_path: str, content_type: str) -> TranscriptionResult:
    return PendingTranscriptionProvider().transcribe(audio_path, content_type)
