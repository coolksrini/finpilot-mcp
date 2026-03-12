"""Unit tests for finpilot-mcp server and client modules.

These tests run without any external services — all orchestrator calls are mocked.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestOrchestratorClient:
    async def test_default_gateway_url(self):
        from finpilot_mcp.orchestrator_client import OrchestratorClient

        client = OrchestratorClient()
        assert "localhost" in client.gateway_url or "http" in client.gateway_url

    async def test_custom_gateway_url(self):
        from finpilot_mcp.orchestrator_client import OrchestratorClient

        client = OrchestratorClient(gateway_url="http://custom:9999")
        assert client.gateway_url == "http://custom:9999"

    async def test_invoke_workflow_returns_error_on_connection_failure(self):
        from finpilot_mcp.orchestrator_client import OrchestratorClient

        client = OrchestratorClient(gateway_url="http://127.0.0.1:19999")  # nothing there
        result = await client.invoke_workflow("TEST_ACTION", {"key": "value"})
        assert result["status"] == "error"
        assert "error_type" in result


@pytest.mark.asyncio
class TestFinPilotClient:
    async def test_is_cloud_url(self):
        from finpilot_mcp.client import FinPilotClient

        c = FinPilotClient()
        assert c._is_cloud_url("https://drive.google.com/file/xyz")
        assert c._is_cloud_url("http://example.com/file.pdf")
        assert not c._is_cloud_url("/Users/name/Downloads/report.pdf")
        assert not c._is_cloud_url("C:\\Users\\name\\report.pdf")

    async def test_analyze_credit_report_cloud_url(self):
        from finpilot_mcp.client import FinPilotClient

        c = FinPilotClient()
        with patch("finpilot_mcp.client._client") as mock_orch:
            mock_orch.invoke_workflow = AsyncMock(return_value={"status": "success"})
            await c.analyze_credit_report("https://drive.google.com/file/xyz", bureau="cibil")
            call_args = mock_orch.invoke_workflow.call_args
            assert call_args[1]["ui_action"] == "EXTRACT_CREDIT_REPORT"
            assert call_args[1]["data"]["input_type"] == "url"

    async def test_analyze_portfolio_missing_input(self):
        from finpilot_mcp.client import FinPilotClient

        c = FinPilotClient()
        # Neither file_path nor portfolio_data provided — server layer handles this,
        # but test that the orchestrator is still called with input_type="data"
        with patch("finpilot_mcp.client._client") as mock_orch:
            mock_orch.invoke_workflow = AsyncMock(return_value={"status": "error"})
            await c.analyze_portfolio(portfolio_data=None)
            assert mock_orch.invoke_workflow.called

    async def test_optimize_loans(self):
        from finpilot_mcp.client import FinPilotClient

        c = FinPilotClient()
        loans = [{"type": "personal_loan", "outstanding": 500000, "apr": 16.5}]
        with patch("finpilot_mcp.client._client") as mock_orch:
            mock_orch.optimize_loans = AsyncMock(return_value={"status": "success", "savings": 60000})
            result = await c.optimize_loans(loans=loans)
            assert result["status"] == "success"
