"""HTTP client for FinPilot API Gateway and A2A Orchestrator.

ARCHITECTURE:
- Local Development: Calls ADK Orchestrator directly via A2A protocol (http://localhost:3000)
- Production: Calls API Gateway via REST API (https://api.finpilot.ai)

The gateway is just a proxy with rate limiting. For local dev, we bypass it.
"""

from typing import Any

import httpx

from finpilot_mcp.config import settings
from finpilot_mcp.constants import ENDPOINTS


class FinPilotAPIError(Exception):
    """Error calling FinPilot API."""
    
    def __init__(self, status_code: int, message: str, details: dict | None = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(f"API Error {status_code}: {message}")


class FinPilotClient:
    """Client for FinPilot API Gateway.
    
    Handles authentication, requests, and error handling.
    """
    
    def __init__(self):
        """Initialize client with settings."""
        self.base_url = settings.effective_backend_url
        self.timeout = settings.request_timeout
        self.upload_timeout = settings.upload_timeout
    
    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authentication."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "finpilot-mcp/0.1.0",
        }
        
        # Add authentication if available
        if settings.jwt_token:
            headers["Authorization"] = f"Bearer {settings.jwt_token}"
        elif settings.api_key:
            headers["X-API-Key"] = settings.api_key
        
        return headers
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        json: dict | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Make HTTP request to API gateway.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            json: Request body (for POST/PUT)
            timeout: Request timeout (uses default if not specified)
            
        Returns:
            Response JSON
            
        Raises:
            FinPilotAPIError: If request fails
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        timeout_val = timeout or self.timeout
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    timeout=timeout_val,
                )
                
                # Check for errors
                if response.status_code >= 400:
                    error_data = response.json() if response.content else {}
                    raise FinPilotAPIError(
                        status_code=response.status_code,
                        message=error_data.get("message", "API request failed"),
                        details=error_data,
                    )
                
                return response.json()
                
        except httpx.TimeoutException as e:
            raise FinPilotAPIError(
                status_code=504,
                message="Request timeout",
                details={"error": str(e)},
            )
        except httpx.RequestError as e:
            raise FinPilotAPIError(
                status_code=503,
                message="Failed to connect to API",
                details={"error": str(e)},
            )
    
    # ========================================================================
    # File Helpers — run on the host, never inside Docker
    # ========================================================================

    @staticmethod
    def _is_cloud_url(path: str) -> bool:
        """Return True if path is a cloud URL (Google Drive, OneDrive, etc.)."""
        return path.startswith("http://") or path.startswith("https://")

    async def _read_file_bytes(self, file_path: str) -> bytes:
        """Read a local file, returning raw bytes.

        Only for local paths — cloud URLs are handled by the orchestrator
        (which has registered OAuth clients for Google Drive / OneDrive).
        """
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

        Args:
            file_path: Local path (/Users/name/file.pdf) or cloud URL (Google Drive, OneDrive)
            bureau: Credit bureau name (optional)
        """
        if self._is_cloud_url(file_path):
            # Cloud URL: orchestrator owns the OAuth/download pipeline
            data: dict[str, Any] = {"input_type": "url", "url": file_path, "bureau": bureau}
        else:
            # Local file: extract text on the host — orchestrator (Docker) can't see host paths
            extracted_text, page_count = await self._extract_pdf_text(file_path)
            data = {
                "input_type": "text",
                "extracted_text": extracted_text,
                "page_count": page_count,
                "bureau": bureau,
            }

        if settings.is_local_dev and settings.use_direct_orchestrator:
            from finpilot_mcp.orchestrator_client import orchestrator_client
            return await orchestrator_client.invoke_workflow(
                ui_action="EXTRACT_CREDIT_REPORT",
                data=data,
            )

        # Production: send to API Gateway
        return await self._request(
            method="POST",
            endpoint=ENDPOINTS["credit_analyze"],
            json=data,
            timeout=self.upload_timeout,
        )
    
    async def get_credit_health(self, user_id: str | None = None) -> dict[str, Any]:
        """Get credit health summary.

        LOCAL DEV: Calls orchestrator directly via A2A
        PRODUCTION: Calls API Gateway via REST

        Args:
            user_id: User ID (optional, uses authenticated user if not provided)

        Returns:
            Credit health data
        """
        # For local dev, use orchestrator directly
        if settings.is_local_dev and settings.use_direct_orchestrator:
            from finpilot_mcp.orchestrator_client import orchestrator_client
            return await orchestrator_client.get_credit_health(user_id=user_id)

        # Production: use REST API
        params = {"user_id": user_id} if user_id else {}
        return await self._request(
            method="GET",
            endpoint=ENDPOINTS["credit_health"],
            json=params,
        )
    
    async def analyze_portfolio(
        self,
        file_path: str | None = None,
        portfolio_data: dict | None = None,
    ) -> dict[str, Any]:
        """Analyze investment portfolio.

        input_type contract:
        - Local PDF   → MCP reads bytes on host, sends input_type="base64" with cas_pdf_base64
                        (casparser inside Docker needs actual binary, not extracted text)
        - Cloud URL   → MCP passes URL as-is, sends input_type="url" (orchestrator handles OAuth)
        - Direct data → sends input_type="data" with portfolio_data dict

        Args:
            file_path: Local path (/Users/name/cas.pdf) or cloud URL (Google Drive, OneDrive)
            portfolio_data: Direct portfolio data as a dict (alternative to PDF)
        """
        import base64 as b64

        if file_path and self._is_cloud_url(file_path):
            # Cloud URL: orchestrator owns the OAuth/download pipeline
            data: dict[str, Any] = {"input_type": "url", "url": file_path}
        elif file_path:
            # Local file: read bytes on host, pass base64 to orchestrator
            # Orchestrator decodes to tempfile → casparser reads it
            pdf_bytes = await self._read_file_bytes(file_path)
            data = {"input_type": "base64", "cas_pdf_base64": b64.b64encode(pdf_bytes).decode()}
        else:
            # Direct portfolio data (no PDF)
            data = {"input_type": "data", "portfolio_data": portfolio_data}

        if settings.is_local_dev and settings.use_direct_orchestrator:
            from finpilot_mcp.orchestrator_client import orchestrator_client
            return await orchestrator_client.invoke_workflow(
                ui_action="EXTRACT_SECURITIES",
                data=data,
            )

        return await self._request(
            method="POST",
            endpoint=ENDPOINTS["portfolio_analyze"],
            json=data,
            timeout=self.upload_timeout,
        )
    
    async def optimize_loans(
        self,
        loans: list[dict] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Get loan optimization recommendations.

        LOCAL DEV: Calls orchestrator directly via A2A
        PRODUCTION: Calls API Gateway via REST

        Args:
            loans: List of loan details
            user_id: User ID (uses authenticated user if not provided)

        Returns:
            Optimization recommendations
        """
        # For local dev, use orchestrator directly
        if settings.is_local_dev and settings.use_direct_orchestrator:
            from finpilot_mcp.orchestrator_client import orchestrator_client
            return await orchestrator_client.optimize_loans(loans=loans, user_id=user_id)

        # Production: use REST API
        return await self._request(
            method="POST",
            endpoint=ENDPOINTS["loan_optimize"],
            json={"loans": loans, "user_id": user_id},
        )
    
    async def create_financial_plan(
        self,
        goals: list[dict],
        current_situation: dict,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Create comprehensive financial plan.

        LOCAL DEV: Calls orchestrator directly via A2A
        PRODUCTION: Calls API Gateway via REST

        Args:
            goals: Financial goals
            current_situation: Current financial situation
            user_id: User ID

        Returns:
            Financial plan
        """
        # For local dev, use orchestrator directly
        if settings.is_local_dev and settings.use_direct_orchestrator:
            from finpilot_mcp.orchestrator_client import orchestrator_client
            return await orchestrator_client.create_financial_plan(
                goals=goals,
                current_situation=current_situation,
                user_id=user_id
            )

        # Production: use REST API
        return await self._request(
            method="POST",
            endpoint=ENDPOINTS["financial_plan"],
            json={
                "goals": goals,
                "current_situation": current_situation,
                "user_id": user_id,
            },
        )


# Global client instance
client = FinPilotClient()
