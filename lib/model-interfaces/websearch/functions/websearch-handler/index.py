import os
import json
import boto3
import requests
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets = boto3.client("secretsmanager")


def get_bing_api_key():
    secret_name = os.environ.get("BING_API_KEY_SECRET")
    if not secret_name:
        raise RuntimeError("Missing BING_API_KEY_SECRET env var")

    secret = secrets.get_secret_value(SecretId=secret_name)
    return secret["SecretString"]


def handler(event, context):
    """
    Expected payload:
    {
      "query": "...",
      "sourceMode": "web",
      "userId": "...",
      "sessionId": "...",
      "topK": 5
    }
    """

    logger.info("Received event: %s", json.dumps(event))

    query = event.get("query")
    user_id = event.get("userId")
    session_id = event.get("sessionId")
    top_k = int(event.get("topK", 5))

    if not query:
        return {
            "type": "error",
            "message": "Missing query"
        }

    api_key = get_bing_api_key()

    headers = {
        "Ocp-Apim-Subscription-Key": api_key
    }

    params = {
        "q": query,
        "recency": 7,
        "domains": None
    }

    try:
        response = requests.get(
            "https://api.bing.microsoft.com/v7.0/search",
            headers=headers,
            params=params,
            timeout=10
        )
        response.raise_for_status()
    except Exception as e:
        logger.exception("Web search failed")
        return {
            "type": "error",
            "message": str(e)
        }

    data = response.json()

    results = []
    for item in data.get("webPages", {}).get("value", []):
        results.append({
            "title": item.get("name"),
            "url": item.get("url"),
            "snippet": item.get("snippet")
        })

    return {
        "type": "text",
        "action": "FINAL_RESPONSE",
        "data": {
            "content": "\n\n".join(
                f"- {r['title']}\n  {r['snippet']}\n  {r['url']}"
                for r in results[:top_k]
            ),
            "sources": results[:top_k],
            "sessionId": session_id,
            "userId": user_id
        }
    }
