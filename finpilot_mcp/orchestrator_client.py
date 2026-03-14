"""Simple HTTP client for communicating with ADK Orchestrator.

The orchestrator exposes a JSON-RPC interface via ADK's to_a2a().
We just need to POST messages to it - no complex A2A SDK needed.
"""

import json
import logging
from typing import Any

import httpx

from finpilot_mcp import machine_id as _machine_id
from finpilot_mcp.config import settings

logger = logging.getLogger(__name__)


class OrchestratorClient:
    """Client for invoking the ADK Orchestrator via simple HTTP calls.

    The orchestrator uses deterministic routing based on ui_action in the message.
    """

    def __init__(self, gateway_url: str | None = None):
        """Initialize orchestrator client.

        Args:
            gateway_url: Auth Service URL (default: from settings).
                         Requests are proxied through Auth Service → Orchestrator.
        """
        self.gateway_url = gateway_url or settings.gateway_url

    async def invoke_workflow(
        self,
        ui_action: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke a workflow on the orchestrator via JSON-RPC 2.0.

        Args:
            ui_action: UI action (e.g., "EXTRACT_CREDIT_REPORT", "GET_CREDIT_HEALTH")
            data: Action data

        Returns:
            Response from orchestrator

        Example:
            >>> client = OrchestratorClient()
            >>> result = await client.invoke_workflow(
            ...     "GET_CREDIT_HEALTH",
            ...     {"user_id": "123"}
            ... )
        """
        try:
            # Create A2A JSON-RPC 2.0 message
            # Format: message/send with role=user, parts=[{type: text, text: ...}]
            message_text = json.dumps({"ui_action": ui_action, "data": data})

            jsonrpc_request = {
                "jsonrpc": "2.0",
                "method": "message/send",  # A2A message/send method
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": message_text}],
                        "messageId": str(hash(message_text)),  # Simple message ID
                    }
                },
                "id": 1,
            }

            # Build request headers — include auth and machine ID
            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Machine-ID": _machine_id.get(),
            }
            if settings.api_key:
                headers["Authorization"] = f"Bearer {settings.api_key}"

            # POST JSON-RPC to Auth Service gateway (proxied → Orchestrator)
            # Use longer timeout for large PDFs (up to 2 minutes)
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.gateway_url,
                    json=jsonrpc_request,
                    headers=headers,
                )
                response.raise_for_status()

                # Parse A2A JSON-RPC response
                result = response.json()

                # Extract result from A2A response
                if "result" in result:
                    task = result["result"]

                    # Extract agent response from artifacts
                    if "artifacts" in task and task["artifacts"]:
                        artifact = task["artifacts"][0]  # Get first artifact
                        if "parts" in artifact and artifact["parts"]:
                            part = artifact["parts"][0]  # Get first part
                            if "text" in part:
                                # Try to parse as JSON
                                try:
                                    return json.loads(part["text"])
                                except (json.JSONDecodeError, TypeError):
                                    return {"response": part["text"]}

                    # If no artifacts, return the task itself
                    return task

                elif "error" in result:
                    return {
                        "status": "error",
                        "error": result["error"].get("message", str(result["error"])),
                        "error_type": "JSONRPCError",
                    }
                else:
                    return result

        except httpx.HTTPStatusError as e:
            logger.error(f"Orchestrator HTTP error: {e.response.status_code} - {e.response.text}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "error_type": "HTTPError",
            }
        except Exception as e:
            logger.error(f"Orchestrator invocation failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}

    async def analyze_credit_report(
        self,
        pdf_base64: str | None = None,
        file_uri: str | None = None,
        password: str | None = None,
        bureau: str | None = None,
    ) -> dict[str, Any]:
        """Analyze credit report via orchestrator.

        Args:
            pdf_base64: Base64-encoded PDF content (preferred)
            file_uri: File URI or path to PDF (alternative)
            password: Optional PDF password
            bureau: Credit bureau name (optional)

        Returns:
            Credit analysis result
        """
        data = {"password": password}

        if pdf_base64:
            data["pdf_base64"] = pdf_base64
        elif file_uri:
            data["file_uri"] = file_uri
        else:
            return {"status": "error", "error": "Either pdf_base64 or file_uri is required"}

        if bureau:
            data["bureau"] = bureau

        return await self.invoke_workflow(ui_action="EXTRACT_CREDIT_REPORT", data=data)

    async def analyze_portfolio(
        self,
        file_path: str,
        password: str | None = None,
        pan: str | None = None,
        dob: str | None = None,
    ) -> dict[str, Any]:
        """Analyze portfolio/CAS via orchestrator.

        Args:
            file_path: Path to CAS PDF
            password: Optional PDF password
            pan: PAN for password inference
            dob: DOB for password inference (DDMMYYYY)

        Returns:
            Portfolio analysis result
        """
        return await self.invoke_workflow(
            ui_action="EXTRACT_SECURITIES",
            data={
                "file_path": file_path,
                "password": password,
                "pan": pan,
                "dob": dob,
            },
        )

    async def get_credit_health(
        self,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Get credit health summary via orchestrator.

        Args:
            user_id: Optional user ID

        Returns:
            Credit health summary
        """
        return await self.invoke_workflow(ui_action="GET_CREDIT_HEALTH", data={"user_id": user_id} if user_id else {})

    async def optimize_loans(
        self,
        loans: list[dict] | None = None,
        user_id: str | None = None,
        portfolio_data: dict | None = None,
    ) -> dict[str, Any]:
        """Get loan optimization recommendations via orchestrator.

        Args:
            loans: List of loan details
            user_id: Optional user ID
            portfolio_data: Portfolio holdings from a prior analyze_portfolio call
                            (required for LAMF collateral evaluation)

        Returns:
            Loan optimization recommendations
        """
        return await self.invoke_workflow(
            ui_action="OPTIMIZE_LOANS",
            data={
                "loans": loans,
                "user_id": user_id,
                "portfolio_data": portfolio_data,
            },
        )

    async def create_financial_plan(
        self,
        goals: list[dict],
        current_situation: dict,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Create financial plan via orchestrator.

        Args:
            goals: List of financial goals
            current_situation: Current financial status
            user_id: Optional user ID

        Returns:
            Financial plan
        """
        return await self.invoke_workflow(
            ui_action="CREATE_FINANCIAL_PLAN",
            data={
                "goals": goals,
                "current_situation": current_situation,
                "user_id": user_id,
            },
        )


# Global client instance
orchestrator_client = OrchestratorClient()
