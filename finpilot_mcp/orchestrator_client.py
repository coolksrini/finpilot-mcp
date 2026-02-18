"""Client for communicating with ADK Orchestrator via A2A protocol.

Uses the official A2A SDK client to communicate with the orchestrator.
"""

import json
import logging
from typing import Any, Optional

from a2a.client import ClientFactory, ClientConfig, create_text_message_object
from a2a.types import Message, Role, TextPart

from finpilot_mcp.config import settings

logger = logging.getLogger(__name__)


class OrchestratorClient:
    """Client for invoking the ADK Orchestrator via A2A protocol.

    The orchestrator uses deterministic routing based on ui_action in the message.
    """

    def __init__(self, orchestrator_url: Optional[str] = None):
        """Initialize orchestrator client.

        Args:
            orchestrator_url: URL of the orchestrator (default: from settings)
        """
        self.orchestrator_url = orchestrator_url or settings.effective_orchestrator_url

        # Create A2A client factory with configuration
        self.client_factory = ClientFactory(
            ClientConfig(
                streaming=False,  # We want complete responses, not streaming
                polling=False,    # No polling needed
            )
        )

        # Minimal agent card for the orchestrator
        # In production, you'd fetch this from the orchestrator's /card endpoint
        self.agent_card = {
            "name": "FinPilot Orchestrator",
            "description": "Multi-agent orchestrator for FinPilot",
            "url": self.orchestrator_url,
            "supported_transports": ["jsonrpc"],
        }

    async def invoke_workflow(
        self,
        ui_action: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke a workflow on the orchestrator.

        Args:
            ui_action: UI action (e.g., "EXTRACT_CREDIT_REPORT", "EXTRACT_SECURITIES")
            data: Action data (e.g., {"file_uri": "...", "password": "..."})

        Returns:
            Complete response from orchestrator

        Example:
            >>> client = OrchestratorClient()
            >>> result = await client.invoke_workflow(
            ...     "EXTRACT_CREDIT_REPORT",
            ...     {"file_uri": "file:///path/to/report.pdf"}
            ... )
        """
        try:
            # Create A2A client for the orchestrator
            client = self.client_factory.create(self.agent_card)

            # Format message for orchestrator
            # Orchestrator expects: {"ui_action": "...", "data": {...}}
            message_content = json.dumps({
                "ui_action": ui_action,
                "data": data
            })

            # Create A2A message using helper (sets messageId automatically)
            message = create_text_message_object(content=message_content)

            # Send message and collect response
            response_text = ""
            async for event in client.send_message(message):
                # event can be (Task, Update) or Message
                if isinstance(event, Message):
                    # Extract text from message parts
                    for part in event.parts:
                        if hasattr(part, 'text'):
                            response_text += part.text
                elif isinstance(event, tuple):
                    # (Task, Update) tuple - extract from task
                    task, update = event
                    if hasattr(task, 'final_message') and task.final_message:
                        for part in task.final_message.parts:
                            if hasattr(part, 'text'):
                                response_text += part.text

            # Parse JSON response
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse orchestrator response as JSON: {response_text[:200]}")
                return {"response": response_text}

        except Exception as e:
            logger.error(f"Orchestrator invocation failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__
            }

    async def analyze_credit_report(
        self,
        file_uri: str,
        password: Optional[str] = None,
    ) -> dict[str, Any]:
        """Analyze credit report via orchestrator.

        Args:
            file_uri: File URI or path to PDF
            password: Optional PDF password

        Returns:
            Credit analysis result
        """
        return await self.invoke_workflow(
            ui_action="EXTRACT_CREDIT_REPORT",
            data={
                "file_uri": file_uri,
                "password": password,
            }
        )

    async def analyze_portfolio(
        self,
        file_path: str,
        password: Optional[str] = None,
        pan: Optional[str] = None,
        dob: Optional[str] = None,
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
            }
        )


# Global client instance
orchestrator_client = OrchestratorClient()
