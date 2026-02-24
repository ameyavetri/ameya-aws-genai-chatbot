"""Base interface for IntentClassifier."""

from typing import Protocol


class IntentClassifier(Protocol):
    """Protocol for classifying user intent from prompt."""

    def classify(
        self,
        prompt: str,
        valid_intents: list[str],
        context: dict | None = None,
    ) -> str:
        """
        Classify user intent from prompt.

        Args:
            prompt: User message text
            valid_intents: List of valid intent keys to choose from
            context: Optional context (session_history, workspace_id, locale)

        Returns:
            One of valid_intents, or "general" as fallback
        """
        ...
