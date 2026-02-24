"""Intent-based prompt resolution: IntentPrompts -> STAFFING_PROMPTS -> system_prompts."""

import json
from aws_lambda_powertools import Logger

from adapters.shared.prompts.staffing_prompts import STAFFING_PROMPTS
from adapters.shared.prompts.system_prompts import prompts

logger = Logger()


class IntentPromptResolver:
    """
    Resolves prompts in order: IntentPrompts[detected_intent] -> STAFFING_PROMPTS -> system_prompts.
    """

    def __init__(
        self,
        intent_prompts: dict | None,
        system_prompts: dict | None,
        locale: str = "en",
    ):
        """
        Args:
            intent_prompts: Parsed IntentPrompts from Application (dict or None)
            system_prompts: From record (systemPrompt, condenseSystemPrompt, systemPromptRag)
            locale: Language locale (e.g. "en", "fr-ca")
        """
        self.intent_prompts = intent_prompts or {}
        self.system_prompts = system_prompts or {}
        self.locale = locale

    def resolve(self, detected_intent: str) -> dict:
        """Resolve effective prompts for the given intent."""
        # 1. Try IntentPrompts[detected_intent]
        intent_config = self.intent_prompts.get(detected_intent)
        if intent_config and isinstance(intent_config, dict):
            system_prompt = intent_config.get("system_prompt") or intent_config.get("systemPrompt")
            if system_prompt:
                logger.info("Using IntentPrompts for intent", intent=detected_intent)
                return {
                    "systemPrompt": system_prompt,
                    "condenseSystemPrompt": self.system_prompts.get("condenseSystemPrompt"),
                    "systemPromptRag": self.system_prompts.get("systemPromptRag"),
                }

        # 2. Fall back to STAFFING_PROMPTS
        staffing = STAFFING_PROMPTS.get(self.locale, STAFFING_PROMPTS.get("en", {}))
        intent_staffing = staffing.get(detected_intent)
        if intent_staffing and isinstance(intent_staffing, dict):
            system_prompt = intent_staffing.get("system_prompt")
            if system_prompt:
                logger.info("Using STAFFING_PROMPTS for intent", intent=detected_intent)
                return {
                    "systemPrompt": system_prompt,
                    "condenseSystemPrompt": self.system_prompts.get("condenseSystemPrompt"),
                    "systemPromptRag": self.system_prompts.get("systemPromptRag"),
                }

        # 3. Fall back to record system_prompts or system_prompts defaults
        prompts_locale = prompts.get(self.locale, prompts.get("en", {}))
        return {
            "systemPrompt": self.system_prompts.get("systemPrompt") or prompts_locale.get("conversation_prompt"),
            "condenseSystemPrompt": self.system_prompts.get("condenseSystemPrompt") or prompts_locale.get("condense_question_prompt"),
            "systemPromptRag": self.system_prompts.get("systemPromptRag") or prompts_locale.get("qa_prompt"),
        }


def parse_intent_prompts(intent_prompts_str: str | None) -> dict | None:
    """Parse IntentPrompts JSON string from DynamoDB."""
    if not intent_prompts_str or not str(intent_prompts_str).strip():
        return None
    try:
        return json.loads(intent_prompts_str)
    except json.JSONDecodeError:
        logger.warning("Invalid intentPrompts JSON, ignoring")
        return None
