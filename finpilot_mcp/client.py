"""HTTP client for FinPilot API Gateway and A2A Orchestrator.

ARCHITECTURE:
- Local Development: Calls ADK Orchestrator directly via A2A protocol (http://localhost:3000)
- Production: Calls API Gateway via REST API (https://api.finpilot.ai)

The gateway is just a proxy with rate limiting. For local dev, we bypass it.
"""

from typing import Any, Optional

import httpx

from finpilot_mcp.config import settings
from finpilot_mcp.constants import ENDPOINTS
from finpilot_mcp.a2a_client import SimpleA2AClient


class FinPilotAPIError(Exception):
    """Error calling FinPilot API."""
    
    def __init__(self, status_code: int, message: str, details: Optional[dict] = None):
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
        json: Optional[dict] = None,
        timeout: Optional[float] = None,
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
    # API Methods
    # ========================================================================
    
    async def analyze_credit_report(
        self,
        file_path: str,
        bureau: Optional[str] = None,
    ) -> dict[str, Any]:
        """Analyze credit report.

        LOCAL DEV: Passes local path as file:// URI or cloud URL directly to orchestrator
        PRODUCTION: Reads file and sends base64 to API Gateway

        Args:
            file_path: Local path (/Users/name/file.pdf) or cloud URL (Google Drive, OneDrive)
            bureau: Credit bureau name (optional)
        """
        if settings.is_local_dev and settings.use_direct_orchestrator:
            from finpilot_mcp.orchestrator_client import orchestrator_client

            # Cloud URLs pass through as-is; local paths become file:// URIs
            if file_path.startswith("http://") or file_path.startswith("https://"):
                file_uri = file_path
            else:
                file_uri = f"file://{file_path}" if not file_path.startswith("file://") else file_path

            return await orchestrator_client.analyze_credit_report(file_uri=file_uri, bureau=bureau)

        # Production: read file and encode to base64
        import base64
        if file_path.startswith("http://") or file_path.startswith("https://"):
            async with httpx.AsyncClient() as http:
                response = await http.get(file_path)
                response.raise_for_status()
                pdf_base64 = base64.b64encode(response.content).decode()
        else:
            with open(file_path, "rb") as f:
                pdf_base64 = base64.b64encode(f.read()).decode()

        return await self._request(
            method="POST",
            endpoint=ENDPOINTS["credit_analyze"],
            json={"pdf_base64": pdf_base64, "bureau": bureau},
            timeout=self.upload_timeout,
        )
    
    async def get_credit_health(self, user_id: Optional[str] = None) -> dict[str, Any]:
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
        file_path: Optional[str] = None,
        portfolio_data: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Analyze investment portfolio.

        LOCAL DEV: Passes local path directly or downloads cloud URL to a temp file
        PRODUCTION: Reads file and sends base64 to API Gateway

        Args:
            file_path: Local path (/Users/name/cas.pdf) or cloud URL (Google Drive, OneDrive)
            portfolio_data: Direct portfolio data as a dict (alternative to PDF)
        """
        if settings.is_local_dev and settings.use_direct_orchestrator:
            from finpilot_mcp.orchestrator_client import orchestrator_client

            if file_path:
                if file_path.startswith("http://") or file_path.startswith("https://"):
                    # Download cloud URL to a temp file, then pass path to orchestrator
                    import tempfile
                    from pathlib import Path
                    async with httpx.AsyncClient() as http:
                        response = await http.get(file_path, follow_redirects=True)
                        response.raise_for_status()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(response.content)
                        tmp_path = tmp.name
                    result = await orchestrator_client.analyze_portfolio(file_path=tmp_path)
                    Path(tmp_path).unlink(missing_ok=True)
                    return result
                else:
                    # Local path — pass straight through, no I/O in the MCP layer
                    return await orchestrator_client.analyze_portfolio(file_path=file_path)

            if portfolio_data:
                return await orchestrator_client.analyze_portfolio(file_path=None)

        # Production: read file and encode to base64
        import base64
        cas_pdf_base64 = None
        if file_path:
            if file_path.startswith("http://") or file_path.startswith("https://"):
                async with httpx.AsyncClient() as http:
                    response = await http.get(file_path, follow_redirects=True)
                    response.raise_for_status()
                    cas_pdf_base64 = base64.b64encode(response.content).decode()
            else:
                with open(file_path, "rb") as f:
                    cas_pdf_base64 = base64.b64encode(f.read()).decode()

        return await self._request(
            method="POST",
            endpoint=ENDPOINTS["portfolio_analyze"],
            json={"cas_pdf_base64": cas_pdf_base64, "portfolio_data": portfolio_data},
            timeout=self.upload_timeout,
        )
    
    async def optimize_loans(
        self,
        loans: Optional[list[dict]] = None,
        user_id: Optional[str] = None,
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
        user_id: Optional[str] = None,
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
