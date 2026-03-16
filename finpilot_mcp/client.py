"""HTTP client for FinPilot Auth Service gateway.

All requests flow through the Auth Service (public entry point) which validates
credentials and proxies to the private orchestrator.

    No FINPILOT_API_KEY → guest tier (stateless calculation tools only)
    FINPILOT_API_KEY=fp_...  → authenticated tier (full personal finance tools)
"""

from typing import Any

from finpilot_mcp.orchestrator_client import OrchestratorClient

# Single client instance reused across all tool calls
_client = OrchestratorClient()


class FinPilotAPIError(Exception):
    """Error calling FinPilot API."""

    def __init__(self, status_code: int, message: str, details: dict | None = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(f"API Error {status_code}: {message}")


class FinPilotClient:
    """High-level client for FinPilot tools.

    Wraps OrchestratorClient with file-handling helpers (local PDF extraction,
    base64 encoding) so that the orchestrator always receives structured data
    rather than raw file paths that only exist on the user's machine.
    """

    # ========================================================================
    # File Helpers — run on the host, never inside Docker
    # ========================================================================

    @staticmethod
    def _is_cloud_url(path: str) -> bool:
        """Return True if path is a cloud URL (Google Drive, OneDrive, etc.)."""
        return path.startswith("http://") or path.startswith("https://")

    @staticmethod
    async def _read_file_bytes(file_path: str) -> bytes:
        """Read a local file, returning raw bytes."""
        with open(file_path, "rb") as f:
            return f.read()

    async def _extract_pdf_text(self, file_path: str) -> tuple[str, int]:
        """Extract text from a local PDF on the host machine.

        Returns (full_text, page_count). Runs pdfplumber locally so the
        orchestrator (in Docker) receives text, not a file path or blob.
        """
        from io import BytesIO

        import pdfplumber

        pdf_bytes = await self._read_file_bytes(file_path)
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            parts = []
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                parts.append(f"=== PAGE {i} ===\n\n{text}")
            return "\n\n".join(parts), len(pdf.pages)

    # ========================================================================
    # API Methods
    # ========================================================================

    async def analyze_credit_report(
        self,
        file_path: str,
        bureau: str | None = None,
    ) -> dict[str, Any]:
        """Analyze credit report.

        input_type contract:
        - Local file  → MCP extracts text on host, sends input_type="text" with extracted_text
        - Cloud URL   → MCP passes URL as-is, sends input_type="url" (orchestrator handles OAuth)
        """
        if self._is_cloud_url(file_path):
            data: dict[str, Any] = {"input_type": "url", "url": file_path, "bureau": bureau}
        else:
            extracted_text, page_count = await self._extract_pdf_text(file_path)
            data = {
                "input_type": "text",
                "extracted_text": extracted_text,
                "page_count": page_count,
                "bureau": bureau,
            }
        return await _client.invoke_workflow(ui_action="EXTRACT_CREDIT_REPORT", data=data)

    async def analyze_credit_report_streaming(
        self,
        file_path: str,
        bureau: str | None = None,
    ):
        """Stream credit report analysis — yields progress + result events."""
        if self._is_cloud_url(file_path):
            data: dict[str, Any] = {"input_type": "url", "url": file_path, "bureau": bureau}
        else:
            extracted_text, page_count = await self._extract_pdf_text(file_path)
            data = {
                "input_type": "text",
                "extracted_text": extracted_text,
                "page_count": page_count,
                "bureau": bureau,
            }
        async for event in _client.invoke_workflow_streaming(
            ui_action="EXTRACT_CREDIT_REPORT", data=data
        ):
            yield event

    async def get_credit_health(self, user_id: str | None = None) -> dict[str, Any]:
        """Get credit health summary."""
        return await _client.get_credit_health(user_id=user_id)

    async def analyze_portfolio(
        self,
        file_path: str | None = None,
        portfolio_data: dict | None = None,
    ) -> dict[str, Any]:
        """Analyze investment portfolio.

        input_type contract:
        - Local PDF   → MCP reads bytes on host, sends input_type="base64"
        - Cloud URL   → MCP passes URL as-is, sends input_type="url"
        - Direct data → sends input_type="data" with portfolio_data dict
        """
        import base64 as b64

        if file_path and self._is_cloud_url(file_path):
            data: dict[str, Any] = {"input_type": "url", "url": file_path}
        elif file_path:
            pdf_bytes = await self._read_file_bytes(file_path)
            data = {"input_type": "base64", "cas_pdf_base64": b64.b64encode(pdf_bytes).decode()}
        else:
            data = {"input_type": "data", "portfolio_data": portfolio_data}

        return await _client.invoke_workflow(ui_action="EXTRACT_SECURITIES", data=data)

    async def optimize_loans(
        self,
        loans: list[dict] | None = None,
        user_id: str | None = None,
        portfolio_data: dict | None = None,
    ) -> dict[str, Any]:
        """Get loan optimization recommendations."""
        return await _client.optimize_loans(loans=loans, user_id=user_id, portfolio_data=portfolio_data)

    async def create_financial_plan(
        self,
        goals: list[dict],
        current_situation: dict,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Create comprehensive financial plan."""
        return await _client.create_financial_plan(
            goals=goals,
            current_situation=current_situation,
            user_id=user_id,
        )


# Global client instance
client = FinPilotClient()
