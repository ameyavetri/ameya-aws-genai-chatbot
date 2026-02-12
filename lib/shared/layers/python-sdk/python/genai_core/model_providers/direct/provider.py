import os
import re
from abc import ABC
from typing import Any, Optional

from aws_lambda_powertools import Logger

import genai_core.clients
import genai_core.parameters
from genai_core.types import EmbeddingsModel, Modality, ModelInterface, Provider

from ..types import ModelProvider

SAGEMAKER_RAG_MODELS_ENDPOINT = os.environ.get("SAGEMAKER_RAG_MODELS_ENDPOINT")
logger = Logger()

# Known embedding dimensions for vector index creation (not provided by Bedrock/OpenAI list APIs).
# Extended as new models are released; unknown models default to 1024.
BEDROCK_EMBEDDING_DIMENSIONS: dict[str, int] = {
    "amazon.titan-embed-text-v1": 1536,
    "amazon.titan-embed-text-v2:0": 256,
    "amazon.titan-embed-image-v1": 1024,
    "cohere.embed-english-v3": 1024,
    "cohere.embed-multilingual-v3": 1024,
    "cohere.embed-english-v2": 1024,
    "cohere.embed-multilingual-v2": 1024,
}
OPENAI_EMBEDDING_DIMENSIONS: dict[str, int] = {
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}
DEFAULT_EMBEDDING_DIMENSIONS = 1024


class DirectModelProvider(ModelProvider, ABC):
    """Provider that connects directly to model services"""

    def list_models(self) -> list[dict[str, Any]]:
        """
        List available models by querying each provider directly

        Returns:
            List of model information dictionaries
        """
        models = []

        # Get Bedrock models
        bedrock_models = _list_bedrock_models()
        if bedrock_models:
            models.extend(bedrock_models)

        bedrock_cris_models = _list_bedrock_cris_models()
        if bedrock_cris_models:
            models.extend(bedrock_cris_models)

        fine_tuned_models = _list_bedrock_finetuned_models()
        if fine_tuned_models:
            models.extend(fine_tuned_models)

        # Get Bedrock agent models
        bedrock_agent_models = _list_bedrock_agent_models()
        if bedrock_agent_models:
            models.extend(bedrock_agent_models)

        # Get SageMaker models
        sagemaker_models = _list_sagemaker_models()
        if sagemaker_models:
            models.extend(sagemaker_models)

        # Get OpenAI models
        openai_models = _list_openai_models()
        if openai_models:
            models.extend(openai_models)

        # Get Azure OpenAI models
        azure_openai_models = _list_azure_openai_models()
        if azure_openai_models:
            models.extend(azure_openai_models)

        return models

    def get_embedding_models(self) -> list[dict[str, Any]]:
        """Discover embedding models from Bedrock and OpenAI (no hardcoded list from config)."""
        models = []
        models.extend(_list_bedrock_embedding_models())
        models.extend(_list_openai_embedding_models())
        if SAGEMAKER_RAG_MODELS_ENDPOINT:
            config = genai_core.parameters.get_config()
            rag = config.get("rag") or {}
            sagemaker_models = rag.get("embeddingsModels") or []
            sagemaker_models = [
                x for x in sagemaker_models if x.get("provider") == "sagemaker"
            ]
            models.extend(sagemaker_models)
        else:
            models = [x for x in models if x.get("provider") != "sagemaker"]
        if models and not any(m.get("default") for m in models):
            models[0]["default"] = True
        return models

    def get_embeddings_model(
        self, provider: Provider, name: str
    ) -> Optional[EmbeddingsModel]:
        """Resolve embedding model by provider+name from discovered list (Bedrock/OpenAI)."""
        provider_str = provider.value if hasattr(provider, "value") else provider
        for model in self.get_embedding_models():
            if model.get("provider") == provider_str and model.get("name") == name:
                return EmbeddingsModel(**model)
        return None

    def get_model_modalities(self, model_id: str) -> list[str]:
        try:
            model_name = model_id.split("::")[1]
            models = self.list_models()
            model = next((m for m in models if m.get("name") == model_name), None)

            if model is None:
                raise genai_core.types.CommonError(f"Model {model_id} not found")

            return model.get("outputModalities", [])
        except IndexError:
            raise genai_core.types.CommonError(
                f"Invalid model ID format: {model_id}"
            ) from None


def _list_openai_models():
    openai = genai_core.clients.get_openai_client()
    if not openai:
        return None

    models = []
    for model in openai.models.list():
        if model.id.startswith("gpt"):
            models.append(
                {
                    "provider": Provider.OPENAI.value,
                    "name": model.id,
                    "streaming": True,
                    "inputModalities": [Modality.TEXT.value],
                    "outputModalities": [Modality.TEXT.value],
                    "interface": ModelInterface.LANGCHAIN.value,
                    "ragSupported": True,
                    "bedrockGuardrails": True,
                }
            )

    return models


def _list_azure_openai_models():
    # azure openai model are listed, comma separated in
    # AZURE_OPENAI_MODELS variable in external API secret
    models = genai_core.parameters.get_external_api_key("AZURE_OPENAI_MODELS") or ""
    if not models:
        return None
    return [
        {
            "provider": Provider.AZURE_OPENAI.value,
            "name": model,
            "streaming": True,
            "inputModalities": [Modality.TEXT.value],
            "outputModalities": [Modality.TEXT.value],
            "interface": ModelInterface.LANGCHAIN.value,
            "ragSupported": True,
            "bedrockGuardrails": True,
        }
        for model in models.split(",")
    ]


# Based on the table (Need to support both document and sytem prompt)
# https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference-supported-models-features.html
def _does_model_support_documents(model_name):
    return (
        not re.match(r"^ai21.jamba*", model_name)
        and not re.match(r"^ai21.j2*", model_name)
        and not re.match(r"^amazon.titan-t*", model_name)
        and not re.match(r"^cohere.command-light*", model_name)
        and not re.match(r"^cohere.command-text*", model_name)
        and not re.match(r"^mistral.mistral-7b-instruct-*", model_name)
        and not re.match(r"^mistral.mistral-small*", model_name)
        and not re.match(r"^amazon.nova-reel*", model_name)
        and not re.match(r"^amazon.nova-canvas*", model_name)
        and not re.match(r"^amazon.nova-micro*", model_name)
    )


def _create_bedrock_model_profile(bedrock_model: dict, model_name: str) -> dict:
    model = {
        "provider": Provider.BEDROCK.value,
        "name": model_name,
        "streaming": bedrock_model.get("responseStreamingSupported", False),
        "inputModalities": bedrock_model["inputModalities"],
        "outputModalities": bedrock_model["outputModalities"],
        "interface": ModelInterface.LANGCHAIN.value,
        "ragSupported": True,
        "bedrockGuardrails": True,
    }

    if _does_model_support_documents(model["name"]):
        model["inputModalities"].append("DOCUMENT")
    return model


def _list_cross_region_inference_profiles():
    bedrock = genai_core.clients.get_bedrock_client(service_name="bedrock")
    response = bedrock.list_inference_profiles()

    return {
        inference_profile["models"][0]["modelArn"].split("/")[1]: inference_profile[
            "inferenceProfileId"
        ]
        for inference_profile in response.get("inferenceProfileSummaries", [])
        if (
            inference_profile.get("status") == "ACTIVE"
            and inference_profile.get("type") == "SYSTEM_DEFINED"
        )
    }


def _list_bedrock_cris_models():
    try:
        cross_region_profiles = _list_cross_region_inference_profiles()
        bedrock_client = genai_core.clients.get_bedrock_client(service_name="bedrock")
        all_models = bedrock_client.list_foundation_models()["modelSummaries"]

        return [
            _create_bedrock_model_profile(
                model, cross_region_profiles[model["modelId"]]
            )
            for model in all_models
            if genai_core.types.InferenceType.INFERENCE_PROFILE.value
            in model["inferenceTypesSupported"]
        ]
    except Exception as e:
        logger.error(f"Error listing cross region inference profiles models: {e}")
        return None


def _list_bedrock_models():
    try:
        bedrock = genai_core.clients.get_bedrock_client(service_name="bedrock")
        if not bedrock:
            return None

        # Do not filter by inference type so all models are listed (e.g. Claude 4.5,
        # latest Sonnet/Haiku). Filtering by ON_DEMAND alone can hide newer models.
        response = bedrock.list_foundation_models()
        bedrock_models = [
            m
            for m in response.get("modelSummaries", [])
            if m.get("modelLifecycle", {}).get("status")
            == genai_core.types.ModelStatus.ACTIVE.value
        ]

        models = []
        for bedrock_model in bedrock_models:
            # Exclude embeddings models
            if (
                "inputModalities" in bedrock_model
                and "outputModalities" in bedrock_model
                and (
                    Modality.EMBEDDING.value
                    in bedrock_model.get("outputModalities", [])
                )
            ):
                continue
            models.append(
                _create_bedrock_model_profile(bedrock_model, bedrock_model["modelId"])
            )

        return models
    except Exception as e:
        logger.error(f"Error listing Bedrock models: {e}")
        return None


def _list_bedrock_embedding_models() -> list[dict[str, Any]]:
    """List embedding models from Bedrock via list_foundation_models(byOutputModality=EMBEDDING)."""
    try:
        bedrock = genai_core.clients.get_bedrock_client(service_name="bedrock")
        if not bedrock:
            return []
        response = bedrock.list_foundation_models(byOutputModality="EMBEDDING")
        summaries = response.get("modelSummaries", [])
        models = []
        for m in summaries:
            if m.get("modelLifecycle", {}).get("status") != genai_core.types.ModelStatus.ACTIVE.value:
                continue
            model_id = m.get("modelId", "")
            dimensions = BEDROCK_EMBEDDING_DIMENSIONS.get(
                model_id, DEFAULT_EMBEDDING_DIMENSIONS
            )
            models.append({
                "provider": Provider.BEDROCK.value,
                "name": model_id,
                "dimensions": dimensions,
                "default": False,
            })
        return models
    except Exception as e:
        logger.error(f"Error listing Bedrock embedding models: {e}")
        return []


def _list_openai_embedding_models() -> list[dict[str, Any]]:
    """List embedding models from OpenAI API (models that support embeddings)."""
    try:
        openai_client = genai_core.clients.get_openai_client()
        if not openai_client:
            return []
        models = []
        for model in openai_client.models.list():
            if "embed" not in model.id.lower():
                continue
            dimensions = OPENAI_EMBEDDING_DIMENSIONS.get(
                model.id, DEFAULT_EMBEDDING_DIMENSIONS
            )
            models.append({
                "provider": Provider.OPENAI.value,
                "name": model.id,
                "dimensions": dimensions,
                "default": False,
            })
        return models
    except Exception as e:
        logger.error(f"Error listing OpenAI embedding models: {e}")
        return []


def _list_bedrock_finetuned_models():
    try:
        bedrock = genai_core.clients.get_bedrock_client(service_name="bedrock")
        if not bedrock:
            return None

        response = bedrock.list_custom_models()
        bedrock_custom_models = response.get("modelSummaries", [])

        models = [
            {
                "provider": Provider.BEDROCK.value,
                "name": f"{model['modelName']} (base model: {model['baseModelName']})",
                "streaming": model.get("responseStreamingSupported", False),
                "inputModalities": model["inputModalities"],
                "outputModalities": model["outputModalities"],
                "interface": ModelInterface.LANGCHAIN.value,
                "ragSupported": True,
            }
            for model in bedrock_custom_models
            # Exclude embeddings and stable diffusion models
            if "inputModalities" in model
            and "outputModalities" in model
            and Modality.EMBEDDING.value not in model.get("outputModalities", [])
            and Modality.IMAGE.value not in model.get("outputModalities", [])
        ]

        return models
    except Exception as e:
        logger.error(f"Error listing fine-tuned Bedrock models: {e}")
        return None


def _list_bedrock_agent_models():
    """
    List Bedrock agent models if enabled in the config

    Returns:
        list[dict[str, Any]]: List of Bedrock agent model information dictionaries
    """
    try:
        # Check if Bedrock agent is enabled via environment variables
        agent_enabled = os.environ.get("BEDROCK_AGENT_ENABLED") == "true"
        agent_id = os.environ.get("BEDROCK_AGENT_ID")

        if not agent_enabled:
            return None

        # If a specific agent ID is provided, just add that one
        if agent_id:
            return [
                {
                    "provider": Provider.BEDROCK.value,
                    "name": "bedrock_agent",
                    "streaming": False,  # Agents don't support streaming
                    "inputModalities": [
                        Modality.TEXT.value,
                        Modality.IMAGE.value,
                        "DOCUMENT",
                    ],
                    "outputModalities": [Modality.TEXT.value],
                    "interface": ModelInterface.LANGCHAIN.value,
                    "ragSupported": True,
                    "bedrockGuardrails": True,
                    "displayName": f"Bedrock Agent: {agent_id}",
                }
            ]

        # If no specific agent ID is provided, list all available agents
        from genai_core.bedrock_agent import list_agents

        agents = list_agents()
        if not agents:
            logger.warning("No Bedrock agents found in the account")
            return None

        models = []
        for agent in agents:
            agent_id = agent.get("agentId")
            agent_name = agent.get("agentName")

            # Create a model entry for each agent
            models.append(
                {
                    "provider": Provider.BEDROCK.value,
                    "name": f"Agent_{agent_name.replace(' ', '_')}_{agent_id}",
                    "streaming": False,  # Agents don't support streaming
                    "inputModalities": [
                        Modality.TEXT.value,
                        Modality.IMAGE.value,
                        "DOCUMENT",
                    ],
                    "outputModalities": [Modality.TEXT.value],
                    "interface": ModelInterface.LANGCHAIN.value,
                    "ragSupported": True,
                    "bedrockGuardrails": True,
                    "displayName": f"Bedrock Agent: {agent_name}",
                }
            )

        return models
    except Exception as e:
        logger.error(f"Error listing Bedrock agent models: {e}")
        return None


def _list_sagemaker_models():
    models = genai_core.parameters.get_sagemaker_models()

    return [
        {
            "provider": Provider.SAGEMAKER.value,
            "name": model["name"],
            "streaming": model.get("responseStreamingSupported", False),
            "inputModalities": model["inputModalities"],
            "outputModalities": model["outputModalities"],
            "interface": model["interface"],
            "ragSupported": model["ragSupported"],
            # Only langchain interface supports bedrock ApplyGuardrail api
            "bedrockGuardrails": model["interface"] != "multimodal",
        }
        for model in models
    ]
