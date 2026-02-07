import os
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
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
#from utils.intent_detector import IntentDetector

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


def _format_connector_context_block(
    items: List[Dict[str, Any]], source_label: str
) -> str:
    """
    Format connector items with citation labels and source attribution (Part 5).
    Each entry shows [N] title, URL, Notes, and "Source: <source_label>".
    """
    if not items:
        return ""
    lines = ["## External Data Source Results"]
    for i, it in enumerate(items, start=1):
        t = (it.get("title") or it.get("source") or "External Data Source").strip()
        u = (it.get("source_url") or it.get("url") or "").strip()
        s = (it.get("snippet") or it.get("content") or "").strip()
        if isinstance(s, dict):
            s = str(s)
        lines.append(f"[{i}] {t}".strip())
        lines.append(f"Source: {source_label}")
        if u:
            lines.append(f"URL: {u}")
        if s:
            lines.append(f"Notes: {s}")
        lines.append("")  # blank line
    return "\n".join(lines).strip()


def resolve_context_for_prompt(
    prompt: str,
    source_mode: str,
    workspace_id: str,
    user_id: str,
    application_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build context block for the LLM and connector citations/sources (Part 5).

    Returns a dict with:
      - context_block: string to prepend into the LLM prompt
      - connector_citations: list of {title, url, source} for UI
      - connector_sources: list of {connector_id, connector_type, connector_name, citation_count}
    """
    mode = _normalize_source_mode(source_mode)

    internal_items: List[Dict[str, Any]] = []
    web_items: List[Dict[str, Any]] = []
    connector_items: List[Dict[str, Any]] = []
    connector_citations: List[Dict[str, Any]] = []
    connector_sources: List[Dict[str, Any]] = []

    # ---- INTERNAL RAG (hook later) ----
    if mode in ["internal", "hybrid"]:
        # TODO (next step): call your existing RAG retriever using workspace_id.
        internal_items = []

    # ---- WEB SEARCH (hook later) ----
    if mode in ["web", "hybrid"]:
        web_items = []

    # ---- CONNECTOR CONTEXT (Phase 5) ----
    connectors_table_name = os.getenv("CONNECTORS_TABLE_NAME")
    if connectors_table_name and workspace_id:
        try:
            from genai_core.connectors import registry as connector_registry
            from genai_core.connectors import intent as connector_intent
            from genai_core.connectors import orchestrator as connector_orchestrator

            if application_id:
                connectors = connector_registry.get_connectors_for_application(
                    workspace_id=workspace_id, application_id=application_id
                )
            else:
                all_connectors = connector_registry.list_connectors(workspace_id=workspace_id)
                connectors = [
                    c
                    for c in all_connectors
                    if c.get("status", "active") == "active"
                    and not c.get("application_ids")
                ]

            if connectors:
                intent_analysis = connector_intent.detect_connector_intent(prompt)
                if intent_analysis.get("needs_connector"):
                    selected_connector = None
                    if intent_analysis.get("connector_id"):
                        selected_connector = next(
                            (
                                c
                                for c in connectors
                                if c.get("connector_id") == intent_analysis["connector_id"]
                            ),
                            None,
                        )
                    if not selected_connector and connectors:
                        selected_connector = connectors[0]

                    if selected_connector:
                        connector_id = selected_connector.get("connector_id")
                        result = connector_orchestrator.execute_query(
                            workspace_id=workspace_id,
                            connector_id=connector_id,
                            user_prompt=prompt,
                            intent=intent_analysis.get("intent"),
                            params=intent_analysis.get("params"),
                            application_id=application_id,
                        )

                        raw_items = result.get("items", [])
                        connector_name = (
                            selected_connector.get("name")
                            or selected_connector.get("connector_type")
                            or selected_connector.get("type")
                            or "External"
                        )
                        connector_type = (
                            selected_connector.get("connector_type")
                            or selected_connector.get("type")
                            or "connector"
                        )

                        for item in raw_items:
                            title = (
                                item.get("title")
                                or item.get("source")
                                or item.get("connector_name")
                                or "External Data Source"
                            )
                            url = item.get("source_url") or item.get("url") or ""
                            snippet = item.get("content") or item.get("snippet") or ""
                            if isinstance(snippet, dict):
                                snippet = str(snippet)
                            source = (
                                item.get("connector_name")
                                or item.get("source")
                                or connector_name
                            )
                            connector_items.append({
                                "title": title,
                                "snippet": snippet,
                                "url": url,
                                "source_url": url,
                                "source": source,
                            })
                            connector_citations.append({
                                "title": title if isinstance(title, str) else str(title),
                                "url": url,
                                "source": source if isinstance(source, str) else str(source),
                            })

                        if connector_items:
                            connector_sources.append({
                                "connector_id": connector_id,
                                "connector_type": connector_type,
                                "connector_name": connector_name,
                                "citation_count": len(connector_items),
                            })

        except Exception as exc:
            logger.warning(
                f"Connector context retrieval failed: {exc}", exc_info=True
            )
            connector_items = []
            connector_citations = []
            connector_sources = []

    parts = []
    internal_block = _format_context_block(
        "Internal Knowledge Base Results", internal_items
    )
    if internal_block:
        parts.append(internal_block)

    web_block = _format_context_block("Internet Search Results", web_items)
    if web_block:
        parts.append(web_block)

    if connector_items and connector_sources:
        source_label = connector_sources[0].get("connector_name", "External Data Source")
        connector_block = _format_connector_context_block(
            connector_items, source_label
        )
        if connector_block:
            parts.append(connector_block)
        # Part 10: logging and metrics when connector context is used
        first_source = connector_sources[0]
        logger.info(
            "connector context used in prompt",
            workspace_id=workspace_id,
            connector_id=first_source.get("connector_id"),
            connector_type=first_source.get("connector_type"),
            operation="resolve_context_for_prompt",
            intent_matched=True,
        )
        try:
            from genai_core.connectors import metrics as connector_metrics

            connector_metrics.put_connector_context_used(workspace_id)
        except Exception:  # noqa: S110
            pass

    context_block = "\n\n".join(parts).strip()

    return {
        "context_block": context_block,
        "connector_citations": connector_citations,
        "connector_sources": connector_sources,
    }


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
    locale = data.get("locale", "en") 
    
    if not session_id:
        session_id = str(uuid.uuid4())
    
    # ==================== NEW: Intent Detection & JD Extraction ====================
    from utils.intent_detector import IntentDetector
    
    # Get session history for context
    from genai_core.langchain import DynamoDBChatMessageHistory
    chat_history = DynamoDBChatMessageHistory(
        table_name=os.environ["SESSIONS_TABLE_NAME"],
        session_id=session_id,
        user_id=user_id,
    )
    session_history = chat_history.messages if hasattr(chat_history, 'messages') else []
    
    # Analyze the query
    query_analysis = IntentDetector.analyze_query(
        user_prompt=prompt,
        workspace_id=workspace_id,
        session_history=session_history
    )
    
    detected_intent = query_analysis['intent']
    job_description = query_analysis['job_description']
    clean_query = query_analysis['clean_query']
    requires_rag = query_analysis['requires_rag']
    
    logger.info(
        "Query analysis complete",
        intent=detected_intent.value,
        has_jd=query_analysis['has_jd'],
        requires_rag=requires_rag,
        workspace_id=workspace_id
    )
    
    # Use clean query for processing
    processed_prompt = clean_query
    
    # ==================== END: Intent Detection ====================
    
    # Get adapter with intent and JD context
    adapter = registry.get_adapter(f"{provider}.{model_id}")
    
    adapter.on_llm_new_token = lambda *args, **kwargs: on_llm_new_token(
        user_id, session_id, *args, **kwargs
    )
    
    # Pass intent and JD to the adapter
    model = adapter(
        model_id=model_id,
        mode=mode,
        session_id=session_id,
        user_id=user_id,
        model_kwargs=data.get("modelKwargs", {}),
        user_intent=detected_intent,  # NEW: Pass detected intent
        job_description=job_description,  # NEW: Pass extracted JD
    )
    
    # ==================== Context Building ====================
    connector_sources: List[Dict[str, Any]] = []
    connector_citations: List[Dict[str, Any]] = []
    # For job posting creation with JD, we don't need RAG
    if detected_intent.value == "job_posting_creation" and job_description:
        # Build prompt with JD embedded
        from adapters.shared.prompts.staffing_prompts import STAFFING_PROMPTS
        user_prompt_template = STAFFING_PROMPTS[locale]["job_posting_creation"]["user_prompt_template"]
        augmented_prompt = user_prompt_template.format(
            job_description=job_description,
            user_query=processed_prompt if processed_prompt else "Analyze this job description."
        )
        
        logger.info("Job posting creation mode - JD embedded in prompt")
    
    # For resume assessment, we need RAG + JD
    elif detected_intent.value == "resume_assessment":
        if job_description:
            # JD is embedded in the QA prompt already via adapter
            # Just use the processed query
            augmented_prompt = processed_prompt
            logger.info("Resume assessment mode - will retrieve resumes from RAG")
        else:
            # No JD provided - ask for it
            augmented_prompt = processed_prompt
            logger.warning("Resume assessment without JD - may need to prompt user")
    
    # For QA mode or general, use standard context resolution (Part 5: citations/sources)
    else:
        application_id = data.get("applicationId")
        context_result = resolve_context_for_prompt(
            prompt=processed_prompt,
            source_mode=source_mode,
            workspace_id=workspace_id,
            user_id=user_id,
            application_id=application_id,
        )
        context_block = context_result["context_block"]
        connector_sources = context_result.get("connector_sources", [])
        connector_citations = context_result.get("connector_citations", [])
        augmented_prompt = build_augmented_prompt(processed_prompt, context_block)

    # ==================== Execute Model ====================
    response = model.run(
        prompt=augmented_prompt,
        workspace_id=workspace_id if requires_rag else None,  # Only use workspace for RAG
        user_groups=user_groups,
        images=images,
        documents=documents,
        videos=videos,
        system_prompts=system_prompts,
    )

    logger.debug(response)

    # Merge connector citations and sources into response metadata (Part 5)
    if connector_sources or connector_citations:
        meta = response.get("metadata") or {}
        response["metadata"] = {
            **meta,
            "connector_sources": connector_sources,
            "connector_citations": connector_citations,
        }

    # ==================== Send Response ====================
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
