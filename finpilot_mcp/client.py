"""HTTP client for FinPilot API Gateway."""

from typing import Any, Optional

import httpx

from finpilot_mcp.config import settings
from finpilot_mcp.constants import ENDPOINTS


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
        self.base_url = settings.effective_gateway_url
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
        pdf_base64: str,
        bureau: Optional[str] = None,
    ) -> dict[str, Any]:
        """Analyze credit report.
        
        Args:
            pdf_base64: Base64 encoded PDF content
            bureau: Credit bureau name (optional)
            
        Returns:
            Credit analysis result
        """
        return await self._request(
            method="POST",
            endpoint=ENDPOINTS["credit_analyze"],
            json={"pdf_base64": pdf_base64, "bureau": bureau},
            timeout=self.upload_timeout,
        )
    
    async def get_credit_health(self, user_id: Optional[str] = None) -> dict[str, Any]:
        """Get credit health summary.
        
        Args:
            user_id: User ID (optional, uses authenticated user if not provided)
            
        Returns:
            Credit health data
        """
        params = {"user_id": user_id} if user_id else {}
        return await self._request(
            method="GET",
            endpoint=ENDPOINTS["credit_health"],
            json=params,
        )
    
    async def analyze_portfolio(
        self,
        cas_pdf_base64: Optional[str] = None,
        portfolio_data: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Analyze investment portfolio.
        
        Args:
            cas_pdf_base64: CAS PDF (base64) - NSDL/CDSL statement
            portfolio_data: Direct portfolio data (alternative to PDF)
            
        Returns:
            Portfolio analysis
        """
        return await self._request(
            method="POST",
            endpoint=ENDPOINTS["portfolio_analyze"],
            json={
                "cas_pdf_base64": cas_pdf_base64,
                "portfolio_data": portfolio_data,
            },
            timeout=self.upload_timeout,
        )
    
    async def optimize_loans(
        self,
        loans: Optional[list[dict]] = None,
        user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get loan optimization recommendations.
        
        Args:
            loans: List of loan details
            user_id: User ID (uses authenticated user if not provided)
            
        Returns:
            Optimization recommendations
        """
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
        
        Args:
            goals: Financial goals
            current_situation: Current financial situation
            user_id: User ID
            
        Returns:
            Financial plan
        """
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
