"""Integration test for finpilot-mcp → orchestrator → mcp-core flow.

Tests the complete local development flow:
1. finpilot-mcp MCP tools
2. Orchestrator via A2A
3. mcp-core tools

PREREQUISITES:
- mcp-core running on http://localhost:8001
- orchestrator running on http://localhost:3000
- Test database with schema

Run:
    pytest tests/test_orchestrator_integration.py -v
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestOrchestratorClient:
    """Test A2A client for orchestrator."""

    async def test_orchestrator_client_init(self):
        """Test orchestrator client initialization."""
        from finpilot_mcp.orchestrator_client import OrchestratorClient

        client = OrchestratorClient()
        assert client.orchestrator_url == "http://localhost:3000"
        assert client.agent_card is not None

    async def test_invoke_workflow_creates_message(self):
        """Test that workflow invocation creates proper message structure."""
        import json

        from a2a.client import create_text_message_object

        from finpilot_mcp.orchestrator_client import OrchestratorClient

        OrchestratorClient()

        # Test message creation format
        ui_action = "EXTRACT_CREDIT_REPORT"
        data = {"file_uri": "file:///test.pdf"}

        message_content = json.dumps({
            "ui_action": ui_action,
            "data": data
        })

        # Verify message creation doesn't fail
        message = create_text_message_object(content=message_content)
        assert message is not None
        assert hasattr(message, 'parts')
        assert len(message.parts) > 0


@pytest.mark.asyncio
class TestFinPilotMCPClient:
    """Test finpilot-mcp client with orchestrator integration."""

    async def test_client_uses_orchestrator_in_dev_mode(self):
        """Test that client uses orchestrator in development mode."""
        from finpilot_mcp.client import FinPilotClient
        from finpilot_mcp.config import settings

        # Ensure we're in dev mode
        assert settings.environment == "development"
        assert settings.is_local_dev
        assert settings.use_direct_orchestrator

        client = FinPilotClient()
        assert client.base_url == settings.effective_backend_url

    async def test_analyze_credit_report_calls_orchestrator(self):
        """Test that analyze_credit_report calls orchestrator in dev mode."""
        import base64

        from finpilot_mcp.client import client

        # Create a small test PDF (just header)
        test_pdf = b"%PDF-1.4\n%EOF"
        pdf_base64 = base64.b64encode(test_pdf).decode()

        # Mock orchestrator client module
        with patch('finpilot_mcp.orchestrator_client.orchestrator_client') as mock_orch:
            mock_orch.analyze_credit_report = AsyncMock(
                return_value={
                    "status": "success",
                    "report_id": "test-123"
                }
            )

            result = await client.analyze_credit_report(
                pdf_base64=pdf_base64,
                bureau="cibil"
            )

            # Verify orchestrator was called
            assert mock_orch.analyze_credit_report.called
            assert result["status"] == "success"


@pytest.mark.asyncio
@pytest.mark.skipif(
    True,  # Skip by default - requires running services
    reason="Requires orchestrator and mcp-core to be running"
)
class TestEndToEndFlow:
    """End-to-end integration tests (requires running services)."""

    async def test_complete_credit_report_flow(self):
        """Test complete flow: MCP tool → Orchestrator → mcp-core."""
        import base64

        from finpilot_mcp.server import analyze_credit_report

        # Load a test PDF (you'd need to provide one)
        test_pdf_path = "tests/fixtures/sample_credit_report.pdf"

        with open(test_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        pdf_base64 = base64.b64encode(pdf_bytes).decode()

        # Call MCP tool
        result = await analyze_credit_report(
            pdf_base64=pdf_base64,
            bureau="cibil"
        )

        # Verify response structure
        assert "status" in result
        assert result["status"] in ["success", "error"]

    async def test_complete_portfolio_flow(self):
        """Test complete flow for portfolio analysis."""
        import base64

        from finpilot_mcp.server import analyze_portfolio

        # Load a test CAS PDF
        test_pdf_path = "tests/fixtures/sample_cas.pdf"

        with open(test_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        pdf_base64 = base64.b64encode(pdf_bytes).decode()

        # Call MCP tool
        result = await analyze_portfolio(
            cas_pdf_base64=pdf_base64
        )

        # Verify response structure
        assert "status" in result
        assert result["status"] in ["success", "error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
