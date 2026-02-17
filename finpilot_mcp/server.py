"""FinPilot MCP Server - Public interface for Claude Desktop and VS Code.

Exposes FinPilot capabilities via MCP protocol.
All business logic runs on FinPilot API Gateway (deployed on GCP).
"""

import os
import sys
from typing import Any

from fastmcp import FastMCP

from finpilot_mcp.client import client
from finpilot_mcp.config import settings

# Initialize MCP server
mcp = FastMCP(
    "FinPilot",
    instructions="""
    FinPilot is your AI financial co-pilot for:
    - Credit report analysis and optimization
    - Portfolio analysis and recommendations
    - Loan optimization (switch to LAMF, refinancing)
    - Comprehensive financial planning
    
    All analysis is powered by FinPilot's proprietary algorithms.
    """,
)


# ============================================================================
# MCP Tools - Credit Analysis
# ============================================================================

@mcp.tool()
async def analyze_credit_report(
    pdf_base64: str,
    bureau: str | None = None,
) -> dict[str, Any]:
    """Analyze credit report from CIBIL, Experian, or Equifax.
    
    Args:
        pdf_base64: Base64 encoded PDF content of credit report
        bureau: Credit bureau name (cibil, experian, equifax) - auto-detected if not provided
        
    Returns:
        Comprehensive credit analysis including:
        - Credit score and factors
        - Loan summary with optimization opportunities
        - Payment history and DPD analysis
        - High-rate loan swap recommendations
    """
    try:
        result = await client.analyze_credit_report(pdf_base64, bureau)
        return {
            "status": "success",
            "data": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


@mcp.tool()
async def get_credit_health(user_id: str | None = None) -> dict[str, Any]:
    """Get current credit health summary.
    
    Args:
        user_id: User ID (optional - uses authenticated user if not provided)
        
    Returns:
        Credit health metrics:
        - Current credit score and trend
        - Total debt and EMI burden
        - Credit utilization
        - Recent changes and alerts
    """
    try:
        result = await client.get_credit_health(user_id)
        return {
            "status": "success",
            "data": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


# ============================================================================
# MCP Tools - Portfolio Analysis
# ============================================================================

@mcp.tool()
async def analyze_portfolio(
    cas_pdf_base64: str | None = None,
    portfolio_data: dict | None = None,
) -> dict[str, Any]:
    """Analyze investment portfolio from CAS statement or direct data.
    
    Args:
        cas_pdf_base64: Base64 encoded CAS PDF (NSDL/CDSL consolidated statement)
        portfolio_data: Direct portfolio data (alternative to PDF)
        
    Returns:
        Portfolio analysis including:
        - Holdings breakdown (mutual funds, stocks)
        - Asset allocation
        - Performance metrics (returns, XIRR)
        - Rebalancing recommendations
        - Tax optimization opportunities
    """
    try:
        result = await client.analyze_portfolio(cas_pdf_base64, portfolio_data)
        return {
            "status": "success",
            "data": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


# ============================================================================
# MCP Tools - Loan Optimization
# ============================================================================

@mcp.tool()
async def optimize_loans(
    loans: list[dict] | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Get loan optimization recommendations.
    
    Args:
        loans: List of loans with details (outstanding, apr, emi, tenure)
        user_id: User ID (uses authenticated user's loans if not provided)
        
    Returns:
        Optimization recommendations:
        - LAMF swap opportunities (save on interest by pledging MF/stocks)
        - Refinancing recommendations
        - Prepayment analysis
        - Potential annual savings
    """
    try:
        result = await client.optimize_loans(loans, user_id)
        return {
            "status": "success",
            "data": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


# ============================================================================
# MCP Tools - Financial Planning
# ============================================================================

@mcp.tool()
async def create_financial_plan(
    goals: list[dict],
    current_situation: dict,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Create comprehensive financial plan based on goals and current situation.
    
    Args:
        goals: List of financial goals (retirement, house, education, etc.)
               Each goal: {name, target_amount, target_date, priority}
        current_situation: Current financial status
                          {income, expenses, assets, liabilities, risk_profile}
        user_id: User ID
        
    Returns:
        Comprehensive financial plan:
        - Goal-wise allocation strategy
        - Investment recommendations
        - Insurance requirements
        - Tax optimization strategies
        - Monthly action items
    """
    try:
        result = await client.create_financial_plan(goals, current_situation, user_id)
        return {
            "status": "success",
            "data": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


# ============================================================================
# MCP Resources - User Data
# ============================================================================

@mcp.resource("user://profile")
async def get_user_profile() -> str:
    """Get authenticated user's financial profile."""
    if not settings.has_auth:
        return "No authentication configured. Set FINPILOT_API_KEY or FINPILOT_JWT_TOKEN environment variable."
    
    # TODO: Implement user profile fetching
    return "User profile resource - to be implemented"


@mcp.resource("user://portfolio")
async def get_user_portfolio() -> str:
    """Get authenticated user's investment portfolio."""
    if not settings.has_auth:
        return "No authentication configured. Set FINPILOT_API_KEY or FINPILOT_JWT_TOKEN environment variable."
    
    # TODO: Implement portfolio fetching
    return "User portfolio resource - to be implemented"


# ============================================================================
# MCP Prompts - Templates
# ============================================================================

@mcp.prompt()
def financial_advisor_prompt(user_query: str) -> str:
    """Generate financial advisor prompt for user query.
    
    Args:
        user_query: User's financial question or concern
    """
    return f"""You are a certified financial advisor helping a user with: {user_query}

Provide:
1. Clear analysis of their situation
2. Actionable recommendations
3. Potential risks and considerations
4. Next steps

Use FinPilot tools to:
- Analyze credit reports for debt optimization
- Review portfolio for investment recommendations
- Evaluate loan consolidation opportunities
- Create comprehensive financial plans

Be professional, empathetic, and prioritize the user's financial wellbeing.
"""


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point with CLI argument support.
    
    Security: Secrets (API keys, tokens) MUST come from environment variables.
    CLI only accepts non-sensitive configuration.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="FinPilot MCP Server - AI Financial Co-Pilot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # STDIO mode (for Claude Desktop)
  FINPILOT_API_KEY=your-key python -m finpilot_mcp.server --mode stdio

  # HTTP mode (for testing)
  FINPILOT_API_KEY=your-key python -m finpilot_mcp.server --mode http --port 8002

  # Override gateway URL (e.g., local development)
  FINPILOT_API_KEY=your-key python -m finpilot_mcp.server \\
    --api-gateway-url http://localhost:8000 \\
    --environment development

Security:
  - API keys and tokens MUST be set via environment variables
  - Never pass secrets via command line arguments
  - Set FINPILOT_API_KEY or FINPILOT_JWT_TOKEN in your environment
        """,
    )

    # Transport mode
    parser.add_argument(
        "--mode",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode: stdio (for Claude Desktop) or http (for testing/dev)",
    )

    # Non-sensitive configuration overrides
    parser.add_argument(
        "--api-gateway-url",
        help="Override API Gateway URL (default: https://api.finpilot.ai)",
    )
    parser.add_argument(
        "--environment",
        choices=["production", "staging", "development"],
        help="Environment (default: production)",
    )

    # HTTP mode settings
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="HTTP server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8002,
        help="HTTP server port (default: 8002)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    args = parser.parse_args()

    # Apply non-sensitive CLI overrides to settings
    if args.api_gateway_url:
        settings.api_gateway_url = args.api_gateway_url
    if args.environment:
        settings.environment = args.environment

    # Validate authentication
    if not settings.has_auth:
        print("ERROR: No authentication configured!", file=sys.stderr)
        print("Set FINPILOT_API_KEY or FINPILOT_JWT_TOKEN environment variable.", file=sys.stderr)
        print("\nExample:", file=sys.stderr)
        print("  export FINPILOT_API_KEY=your-api-key-here", file=sys.stderr)
        print("  python -m finpilot_mcp.server --mode stdio", file=sys.stderr)
        sys.exit(1)

    # Run in appropriate mode
    if args.mode == "stdio":
        # STDIO mode - for Claude Desktop
        print(f"[FinPilot MCP] Starting in STDIO mode", file=sys.stderr)
        print(f"[FinPilot MCP] Gateway: {settings.effective_gateway_url}", file=sys.stderr)
        print(f"[FinPilot MCP] Environment: {settings.environment}", file=sys.stderr)

        # Run MCP server in stdio mode
        mcp.run()
    else:
        # HTTP mode - for testing/development
        import uvicorn

        print(f"[FinPilot MCP] Starting HTTP server on http://{args.host}:{args.port}")
        print(f"[FinPilot MCP] Gateway URL: {settings.effective_gateway_url}")
        print(f"[FinPilot MCP] Environment: {settings.environment}")
        print(f"[FinPilot MCP] Docs: http://{args.host}:{args.port}/docs")

        uvicorn.run(
            mcp.http_app,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )


if __name__ == "__main__":
    main()
