"""LLM-based intent classification using Bedrock."""

import os
from aws_lambda_powertools import Logger
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage

from genai_core.clients import get_bedrock_client

logger = Logger()


class LLMClassifier:
    """LLM-based intent classification using a lightweight model."""

    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or os.environ.get(
            "INTENT_CLASSIFIER_MODEL",
            "anthropic.claude-3-haiku-20240307-v1:0",
        )
        if self.model_id.startswith("bedrock::"):
            self.model_id = self.model_id.split("::", 1)[1]

    def classify(
        self,
        prompt: str,
        valid_intents: list[str],
        context: dict | None = None,
    ) -> str:
        """Classify intent using LLM."""
        if not valid_intents:
            return "general"

        valid_str = ", ".join(valid_intents)
        system_prompt = (
            f"You are an intent classifier. Given a user message, respond with exactly one of these intents: {valid_str}. "
            "Reply with only the intent key, no explanation."
        )
        user_prompt = f"Classify this message:\n\n{prompt[:2000]}"

        try:
            bedrock = get_bedrock_client()
            llm = ChatBedrockConverse(
                client=bedrock,
                model=self.model_id,
                temperature=0,
                max_tokens=64,
            )
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            response = llm.invoke(messages)
            content = (
                response.content.strip().lower()
                if hasattr(response, "content")
                else str(response).strip().lower()
            )
            # Extract first word/token if model added extra text
            for intent in valid_intents:
                if intent.lower() in content or content == intent.lower():
                    logger.info("LLM classifier matched intent", intent=intent)
                    return intent
            # Fallback: use first valid intent that appears in response
            for intent in valid_intents:
                if intent.lower() in content:
                    return intent
        except Exception as e:
            logger.warning("LLM classifier failed, falling back to general", error=str(e))

        return "general" if "general" in valid_intents else valid_intents[0]
