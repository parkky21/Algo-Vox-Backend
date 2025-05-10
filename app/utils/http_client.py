import httpx
from typing import Optional, Dict, Any
from livekit.agents.voice import RunContext

async def call_external_api(
    context: RunContext,
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Tool to call an external API from within a voice agent.

    :param method: HTTP method (GET, POST, PUT, DELETE, PATCH)
    :param url: API endpoint
    :param headers: Optional headers
    :param params: Optional query parameters
    :param body: Optional JSON body
    :return: API response
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=body
            )

            content_type = response.headers.get("Content-Type", "")
            data = response.json() if "application/json" in content_type else response.text

            return {
                "status_code": response.status_code,
                "response": data
            }

    except httpx.RequestError as e:
        return {
            "status_code": 500,
            "error": str(e)
        }
    

