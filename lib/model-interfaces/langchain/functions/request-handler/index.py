import os
import json
import uuid
from datetime import datetime
from genai_core.registry import registry
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities import parameters
from aws_lambda_powertools.utilities.batch import BatchProcessor, EventType
from aws_lambda_powertools.utilities.batch.exceptions import BatchProcessingError
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord
from aws_lambda_powertools.utilities.typing import LambdaContext

import adapters  # noqa: F401 Needed to register the adapters
from genai_core.utils.websocket import send_to_client
from genai_core.types import ChatbotAction

processor = BatchProcessor(event_type=EventType.SQS)
tracer = Tracer()
logger = Logger()

AWS_REGION = os.environ["AWS_REGION"]
API_KEYS_SECRETS_ARN = os.environ["API_KEYS_SECRETS_ARN"]

sequence_number = 0

def _normalize_source_mode(source_mode: str) -> str:
    """
    Normalize UI value into one of: internal | web | hybrid
    """
    if not source_mode:
        return "internal"
    source_mode = str(source_mode).strip().lower()
    if source_mode in ["internal", "web", "hybrid"]:
        return source_mode
    return "internal"


def _format_context_block(title: str, items: list) -> str:
    """
    items: list of dicts like { "title": "...", "url": "...", "snippet": "..." }
    """
    if not items:
        return ""
    lines = [f"## {title}"]
    for i, it in enumerate(items, start=1):
        t = (it.get("title") or "").strip()
        u = (it.get("url") or "").strip()
        s = (it.get("snippet") or "").strip()
        lines.append(f"[{i}] {t}".strip())
        if u:
            lines.append(f"URL: {u}")
        if s:
            lines.append(f"Notes: {s}")
        lines.append("")  # blank line
    return "\n".join(lines).strip()


def resolve_context_for_prompt(prompt: str, source_mode: str, workspace_id: str, user_id: str) -> str:
    """
    Phase-2: Minimal stub wiring.
    - INTERNAL: pull RAG context (hook later)
    - WEB: pull web context (hook later)
    - HYBRID: both

    For now, returns a string block you prepend into the LLM prompt.
    """
    mode = _normalize_source_mode(source_mode)

    internal_items = []
    web_items = []

    # ---- INTERNAL RAG (hook later) ----
    if mode in ["internal", "hybrid"]:
        # TODO (next step): call your existing RAG retriever using workspace_id.
        # internal_items should become list of {title,url,snippet} or similar.
        internal_items = []

    # ---- WEB SEARCH (hook later) ----
    if mode in ["web", "hybrid"]:
        # IMPORTANT: This requires Lambda outbound internet (NAT) OR a private web search proxy.
        # TODO (next step): implement web search provider and fill web_items.
        web_items = []

    parts = []
    internal_block = _format_context_block("Internal Knowledge Base Results", internal_items)
    if internal_block:
        parts.append(internal_block)

    web_block = _format_context_block("Internet Search Results", web_items)
    if web_block:
        parts.append(web_block)

    return "\n\n".join(parts).strip()


def build_augmented_prompt(user_prompt: str, context_block: str) -> str:
    """
    Final prompt fed into model.run().
    """
    if not context_block:
        return user_prompt

    return (
        "You are an assistant. Use the context below when helpful. "
        "If the context is insufficient, answer based on your general knowledge.\n\n"
        f"{context_block}\n\n"
        "## User Question\n"
        f"{user_prompt}"
    )


def on_llm_new_token(
    user_id, session_id, self, token, run_id, chunk, parent_run_id, *args, **kwargs
):
    if self.disable_streaming:
        logger.debug("Streaming is disabled, ignoring token")
        return
    if isinstance(token, list):
        # When using the newer Chat objects from Langchain.
        # Token is not a string
        text = ""
        for t in token:
            if "text" in t:
                text = text + t.get("text")
    else:
        text = token
    if text is None or len(text) == 0:
        return
    global sequence_number
    sequence_number += 1
    run_id = str(run_id)

    send_to_client(
        {
            "type": "text",
            "action": ChatbotAction.LLM_NEW_TOKEN.value,
            "userId": user_id,
            "timestamp": str(int(round(datetime.now().timestamp()))),
            "data": {
                "sessionId": session_id,
                "token": {
                    "runId": run_id,
                    "sequenceNumber": sequence_number,
                    "value": text,
                },
            },
        }
    )


def handle_heartbeat(record):
    user_id = record["userId"]
    session_id = record["data"]["sessionId"]

    send_to_client(
        {
            "type": "text",
            "action": ChatbotAction.HEARTBEAT.value,
            "timestamp": str(int(round(datetime.now().timestamp()))),
            "userId": user_id,
            "data": {
                "sessionId": session_id,
            },
        }
    )


def handle_run(record):
    user_id = record["userId"]
    user_groups = record["userGroups"]
    data = record["data"]
    provider = data["provider"]
    model_id = data["modelName"]
    mode = data["mode"]
    prompt = data["text"]
    workspace_id = data.get("workspaceId", None)
    source_mode = data.get("sourceMode", "internal")
    session_id = data.get("sessionId")
    images = data.get("images", [])
    documents = data.get("documents", [])
    videos = data.get("videos", [])
    system_prompts = record.get("systemPrompts", {})
    if not session_id:
        session_id = str(uuid.uuid4())

    adapter = registry.get_adapter(f"{provider}.{model_id}")

    adapter.on_llm_new_token = lambda *args, **kwargs: on_llm_new_token(
        user_id, session_id, *args, **kwargs
    )

    model = adapter(
        model_id=model_id,
        mode=mode,
        session_id=session_id,
        user_id=user_id,
        model_kwargs=data.get("modelKwargs", {}),
    )
    
    context_block = resolve_context_for_prompt(
        prompt=prompt,
        source_mode=source_mode,
        workspace_id=workspace_id,
        user_id=user_id,
    )
    augmented_prompt = build_augmented_prompt(prompt, context_block)

    response = model.run(
        prompt=augmented_prompt,
        workspace_id=workspace_id,
        user_groups=user_groups,
        images=images,
        documents=documents,
        videos=videos,
        system_prompts=system_prompts,
    )

    logger.debug(response)

    send_to_client(
        {
            "type": "text",
            "action": ChatbotAction.FINAL_RESPONSE.value,
            "timestamp": str(int(round(datetime.now().timestamp()))),
            "userId": user_id,
            "userGroups": user_groups,
            "data": response,
        }
    )


@tracer.capture_method
def record_handler(record: SQSRecord):
    payload: str = record.body
    message: dict = json.loads(payload)
    detail: dict = json.loads(message["Message"])
    logger.debug(detail)
    logger.info("details", detail=detail)

    if detail["action"] == ChatbotAction.RUN.value:
        handle_run(detail)
    elif detail["action"] == ChatbotAction.HEARTBEAT.value:
        handle_heartbeat(detail)


def handle_failed_records(records):
    for triplet in records:
        status, error, record = triplet
        payload: str = record.body
        message: dict = json.loads(payload)
        detail: dict = json.loads(message["Message"])
        user_id = detail["userId"]
        data = detail.get("data", {})
        session_id = data.get("sessionId", "")

        message = "⚠️ *Something went wrong*"
        if (
            "An error occurred (ValidationException)" in error
            and "The provided image must have dimensions in set [1280x720]" in error
        ):
            # At this time only one input size is supported by the Nova reel model.
            message = "⚠️ *The provided image must have dimensions of 1280x720.*"
        elif (
            "An error occurred (ValidationException)" in error
            and "The width of the provided image must be within range [320, 4096]"
            in error
        ):
            # At this time only this size is supported by the Nova canvas model.
            message = "⚠️ *The width of the provided image must be within range 320 and 4096 pixels.*"  # noqa
        elif (
            "An error occurred (AccessDeniedException)" in error
            and "You don't have access to the model with the specified model ID"
            in error
        ):
            message = (
                "*This model is not enabled. "
                "Please try again later or contact "
                "an administrator*"
            )
        else:
            logger.error("Unable to process request", error=error)

        send_to_client(
            {
                "type": "text",
                "action": "error",
                "direction": "OUT",
                "userId": user_id,
                "timestamp": str(int(round(datetime.now().timestamp()))),
                "data": {
                    "sessionId": session_id,
                    # Log a vague message because the error can contain
                    # internal information
                    "content": message,
                    "type": "text",
                },
            }
        )


@logger.inject_lambda_context(log_event=False)
@tracer.capture_lambda_handler
def handler(event, context: LambdaContext):
    batch = event["Records"]

    api_keys = parameters.get_secret(API_KEYS_SECRETS_ARN, transform="json")
    for key in api_keys:
        os.environ[key] = api_keys[key]

    try:
        with processor(records=batch, handler=record_handler):
            processed_messages = processor.process()
    except BatchProcessingError as e:
        logger.error(e)

    for message in processed_messages:
        logger.info(
            "Request complete with status " + message[0],
            status=message[0],
            cause=message[1],
        )
    handle_failed_records(
        message for message in processed_messages if message[0] == "fail"
    )

    return processor.response()
