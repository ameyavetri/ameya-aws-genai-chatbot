"""Rule-based intent classifier using regex patterns."""

from aws_lambda_powertools import Logger

from utils.intent_detector import IntentDetector, UserIntent

logger = Logger()


class RuleClassifier:
    """Rule-based intent classification using IntentDetector."""

    def classify(
        self,
        prompt: str,
        valid_intents: list[str],
        context: dict | None = None,
    ) -> str:
        """Classify intent using rule-based IntentDetector."""
        if not valid_intents:
            return "general"

        session_history = None
        workspace_id = None
        if context:
            session_history = context.get("session_history")
            workspace_id = context.get("workspace_id")

        result = IntentDetector.analyze_query(
            user_prompt=prompt,
            workspace_id=workspace_id,
            session_history=session_history,
        )
        detected = result["intent"]
        intent_value = detected.value if hasattr(detected, "value") else str(detected)

        if intent_value in valid_intents:
            logger.info("Rule classifier matched intent", intent=intent_value)
            return intent_value
        if "general" in valid_intents:
            return "general"
        return valid_intents[0] if valid_intents else "general"
