"""Factory for creating prompt resolvers."""

from utils.prompt_resolver.intent_resolver import IntentPromptResolver, parse_intent_prompts


def create_resolver(
    intent_prompts_str: str | None,
    system_prompts: dict | None,
    locale: str = "en",
) -> IntentPromptResolver:
    """
    Create a prompt resolver for the given application and record context.

    Args:
        intent_prompts_str: JSON string from Application.intentPrompts
        system_prompts: From record (systemPrompt, condenseSystemPrompt, systemPromptRag)
        locale: Language locale

    Returns:
        IntentPromptResolver instance
    """
    intent_prompts = parse_intent_prompts(intent_prompts_str)
    return IntentPromptResolver(
        intent_prompts=intent_prompts,
        system_prompts=system_prompts,
        locale=locale,
    )
