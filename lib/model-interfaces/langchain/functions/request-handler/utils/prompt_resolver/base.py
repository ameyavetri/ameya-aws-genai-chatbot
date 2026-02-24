"""Base interface for PromptResolver."""

from typing import Protocol


class PromptResolver(Protocol):
    """Protocol for resolving intent-specific prompts."""

    def resolve(self, detected_intent: str) -> dict:
        """
        Resolve effective system prompts for the given intent.

        Returns:
            Dict with keys: systemPrompt, condenseSystemPrompt, systemPromptRag
            (values may be None to use adapter defaults)
        """
        ...
