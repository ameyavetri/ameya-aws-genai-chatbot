"""Factory for creating the appropriate intent classifier."""

import os

from utils.intent.base import IntentClassifier
from utils.intent.llm_classifier import LLMClassifier
from utils.intent.rule_classifier import RuleClassifier


def create_classifier() -> IntentClassifier:
    """
    Create intent classifier based on INTENT_CLASSIFIER_ENABLED.

    Returns:
        LLMClassifier if enabled, else RuleClassifier
    """
    enabled = os.environ.get("INTENT_CLASSIFIER_ENABLED", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if enabled:
        return LLMClassifier()
    return RuleClassifier()
