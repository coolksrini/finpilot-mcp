"""A2A client for communicating with ADK Orchestrator.

The orchestrator exposes an A2A (Agent-to-Agent) protocol server.
This client sends messages to the orchestrator and receives streamed responses.
"""

import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)


class A2AClient:
    """Client for communicating with ADK agents via A2A protocol.

    The A2A protocol is a standard way to invoke agents and receive streamed responses.
    """

    def __init__(self, base_url: str, timeout: float = 120.0):
        """Initialize A2A client.

        Args:
            base_url: Base URL of the A2A server (e.g., http://localhost:3000)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def send_message(
        self,
        message: str,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send message to agent and stream responses.

        Args:
            message: User message or JSON-formatted request
            session_id: Optional session ID for conversation continuity

        Yields:
            Events from the agent (text, function calls, etc.)
        """
        # Construct A2A request
        request_data = {
            "message": message,
            "session_id": session_id,
        }

        # Send POST request to A2A server
        # A2A servers typically use /invoke or similar endpoint
        url = f"{self.base_url}/invoke"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=request_data) as response:
                    response.raise_for_status()

                    # Stream Server-Sent Events (SSE)
                    async for line in response.aiter_lines():
                        if not line or not line.strip():
                            continue

                        # Parse SSE event
                        if line.startswith("data: "):
                            event_data = line[6:]  # Remove "data: " prefix
                            try:
                                event = json.loads(event_data)
                                yield event
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse event: {event_data}")
                                continue

        except httpx.HTTPStatusError as e:
            logger.error(f"A2A request failed: {e.response.status_code} {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to A2A server: {e}")
            raise

    async def invoke_workflow(
        self,
        ui_action: str,
        data: dict[str, Any],
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Invoke a workflow on the orchestrator.

        The orchestrator uses deterministic routing based on ui_action.

        Args:
            ui_action: UI action (e.g., "EXTRACT_CREDIT_REPORT")
            data: Action data (e.g., {"file_uri": "...", "password": "..."})
            session_id: Optional session ID

        Returns:
            Final response from orchestrator
        """
        # Format message as JSON for orchestrator
        message = json.dumps({
            "ui_action": ui_action,
            "data": data
        })

        # Collect all events
        response_text = ""
        async for event in self.send_message(message, session_id):
            # Extract text from event
            if "content" in event:
                content = event["content"]
                if isinstance(content, dict) and "parts" in content:
                    for part in content["parts"]:
                        if "text" in part:
                            response_text += part["text"]
                elif isinstance(content, str):
                    response_text += content

        # Parse final response
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # If not JSON, return as-is
            return {"response": response_text}


# Simplified client for HTTP-based invocation (alternative to SSE streaming)
class SimpleA2AClient:
    """Simplified A2A client using direct HTTP requests.

    This client sends a request and waits for the complete response.
    No streaming, simpler for basic use cases.
    """

    def __init__(self, base_url: str, timeout: float = 120.0):
        """Initialize simple A2A client.

        Args:
            base_url: Base URL of the orchestrator (e.g., http://localhost:3000)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def invoke(
        self,
        ui_action: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke orchestrator workflow and get complete response.

        Args:
            ui_action: UI action (EXTRACT_CREDIT_REPORT, EXTRACT_SECURITIES, etc.)
            data: Action data

        Returns:
            Complete response from orchestrator
        """
        # Construct request
        request_data = {
            "ui_action": ui_action,
            "data": data
        }

        # For simplicity, call orchestrator's custom endpoint if available
        # Or use standard A2A invoke endpoint
        url = f"{self.base_url}/invoke-workflow"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=request_data)
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Orchestrator request failed: {e.response.status_code}")
            error_data = {}
            try:
                error_data = e.response.json()
            except:
                pass
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}",
                "details": error_data
            }
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to orchestrator: {e}")
            return {
                "status": "error",
                "error": "Connection failed",
                "details": str(e)
            }
