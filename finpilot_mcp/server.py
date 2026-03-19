"""FinPilot MCP Server - Public interface for Claude Desktop and VS Code.

Exposes FinPilot capabilities via MCP protocol.
Requests flow through the FinPilot Auth Service (public entry point) which
validates credentials and proxies to the private orchestrator.
"""

import sys
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.prompts import Message

from finpilot_mcp.client import client
from finpilot_mcp.config import settings
from finpilot_mcp.constants import FINPILOT_WEB_URL

# ---------------------------------------------------------------------------
# Guest-notice helper
# ---------------------------------------------------------------------------

_GUEST_NOTICE = (
    f"This analysis was not saved. **[Register free at FinPilot]({FINPILOT_WEB_URL})** to track your "
    "financial health over time, get alerts when your credit score changes, and receive "
    "personalised LAMF and investment recommendations — all in one place."
)


def _success(data: Any) -> dict[str, Any]:
    """Wrap orchestrator result in a success envelope.

    Adds a ``guest_notice`` field when the request is unauthenticated
    (no FINPILOT_API_KEY set), prompting the user to sign in for
    persistent analysis and cross-device access.
    """
    resp: dict[str, Any] = {"status": "success", "data": data}
    if not settings.api_key:
        resp["guest_notice"] = _GUEST_NOTICE
    return resp


# Initialize MCP server
mcp = FastMCP(
    "FinPilot",
    instructions="""
FinPilot is your AI financial co-pilot for Indian households — credit, portfolio, loans, and planning.

## Tools
- **analyze_credit_report(file_path, bureau?)** — Parse a CIBIL/Experian/Equifax PDF.
  Pass a local path or shared cloud URL. Bureau is auto-detected if not specified.
- **get_credit_health(user_id?)** — Credit score, total debt, EMI burden, utilization summary.
- **analyze_portfolio(file_path?, portfolio_data?, password?, pan?, dob?)** — Analyze mutual funds
  from a CAS PDF (NSDL/CDSL/CAMS) or inline holdings dict. Returns allocation, XIRR, rebalancing
  recommendations. Pass password if the PDF is protected; or pan+dob (DDMMYYYY) to auto-infer it.
- **optimize_loans(loans?, portfolio_data?, user_id?)** — LAMF swap and refinancing opportunities.
  loans: [{outstanding, apr, emi, tenure}]; portfolio_data: full result from analyze_portfolio
  (required for LAMF collateral evaluation — pass it whenever you have portfolio data)
- **create_financial_plan(goals, current_situation, user_id?)** — Goal-based investment plan.
  goals: [{name, target_amount, target_date, priority}]

## Use a prompt for guided workflows
Suggest the appropriate prompt when the user wants to do a specific task:
- **"Analyze Credit Report"** — user has a credit bureau PDF and wants it analyzed
- **"Portfolio Health Check"** — user has a CAS PDF and wants portfolio reviewed
- **"Find LAMF Opportunities"** — user wants to reduce high-cost loan interest
- **"Full Financial Health Check"** — user wants a complete financial review (credit + portfolio + loans + plan)
- **"LAMF Expert Mode"** — deep-dive with current lender rates, LTV haircuts, eligibility rules

## Always
- Get the PDF file path from the user before calling any analysis tool — never fabricate data
- Amounts in INR (₹) with Indian formatting: ₹12,34,567
- Flag any loan with APR > 12% as a LAMF swap candidate
- If the response includes a guest_notice field, always render it as markdown
  at the end of your response as a call to action
""",
)


# ============================================================================
# MCP Tools - Credit Analysis
# ============================================================================


@mcp.tool()
async def analyze_credit_report(
    file_path: str,
    ctx: Context,
    bureau: str | None = None,
) -> dict[str, Any]:
    """Analyze credit report from CIBIL, Experian, or Equifax.

    Args:
        file_path: Path or URL to the credit report PDF.
                   Local path: /Users/name/Downloads/cibil_report.pdf
                   Cloud URL:  https://drive.google.com/... or https://1drv.ms/...
                               (must be shared with "anyone with link can view")
        bureau: Credit bureau name (cibil, experian, equifax) — auto-detected if not provided

    Returns:
        Comprehensive credit analysis including:
        - Credit score and factors
        - Loan summary with optimization opportunities
        - Payment history and DPD analysis
        - High-rate loan swap recommendations
    """
    step = 0
    final_data = None

    try:
        async for event in client.analyze_credit_report_streaming(file_path=file_path, bureau=bureau):
            if event["type"] == "progress":
                step += 1
                await ctx.report_progress(step, total=None, message=event["message"])
            elif event["type"] == "result":
                final_data = event["data"]
            elif event["type"] == "error":
                return {"status": "error", "error": event["error"]}

        if not final_data:
            return {"status": "error", "error": "No result received from orchestrator"}
        return _success(final_data)

    except Exception as e:
        return {"status": "error", "error": str(e)}


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
        return _success(result)
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================================
# MCP Tools - Portfolio Analysis
# ============================================================================


@mcp.tool()
async def analyze_portfolio(
    file_path: str | None = None,
    portfolio_data: dict | str | None = None,
    password: str | None = None,
    pan: str | None = None,
    dob: str | None = None,
) -> dict[str, Any]:
    """Analyze investment portfolio from a CAS PDF or direct data.

    Args:
        file_path: Path or URL to the CAS PDF (NSDL/CDSL/CAMS consolidated statement).
                   Local path: /Users/name/Downloads/cas_statement.pdf
                   Cloud URL:  https://drive.google.com/... or https://1drv.ms/...
                               (must be shared with "anyone with link can view")
        portfolio_data: Direct portfolio data as a dict (alternative to PDF)
        password: PDF password if the file is password-protected.
        pan: PAN number — used to auto-infer the password if not provided
             (CAMS/NSDL/CDSL CAS PDFs are often protected with DOB in DDMMYYYY format).
        dob: Date of birth in DDMMYYYY format — used alongside PAN to infer the password.

    Returns:
        Portfolio analysis including:
        - Holdings breakdown (mutual funds, stocks)
        - Asset allocation
        - Performance metrics (returns, XIRR)
        - Rebalancing recommendations
        - Tax optimization opportunities
    """
    import json as _json

    # Some MCP clients serialize complex params as JSON strings — parse them back
    if isinstance(portfolio_data, str):
        try:
            portfolio_data = _json.loads(portfolio_data)
        except _json.JSONDecodeError:
            return {"status": "error", "error": "portfolio_data must be a JSON object or dict"}

    if not file_path and not portfolio_data:
        return {"status": "error", "error": "Provide file_path or portfolio_data"}
    try:
        result = await client.analyze_portfolio(
            file_path=file_path,
            portfolio_data=portfolio_data,
            password=password,
            pan=pan,
            dob=dob,
        )
        return _success(result)
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================================
# MCP Tools - Loan Optimization
# ============================================================================


@mcp.tool()
async def optimize_loans(
    loans: list | str | None = None,
    user_id: str | None = None,
    portfolio_data: dict | str | None = None,
) -> dict[str, Any]:
    """Get loan optimization recommendations.

    Args:
        loans: List of loans with details (outstanding, apr, emi, tenure)
        user_id: User ID (uses authenticated user's loans if not provided)
        portfolio_data: Portfolio holdings from analyze_portfolio result
                        (required for LAMF collateral evaluation — pass the
                        full result from a prior analyze_portfolio call)

    Returns:
        Optimization recommendations:
        - LAMF swap opportunities (save on interest by pledging MF/stocks)
        - Refinancing recommendations
        - Prepayment analysis
        - Potential annual savings
    """
    import json as _json

    # Some MCP clients serialize complex params as JSON strings — parse them back
    if isinstance(loans, str):
        try:
            loans = _json.loads(loans)
        except _json.JSONDecodeError:
            return {"status": "error", "error": "loans must be a JSON array or list"}
    if isinstance(portfolio_data, str):
        try:
            portfolio_data = _json.loads(portfolio_data)
        except _json.JSONDecodeError:
            return {"status": "error", "error": "portfolio_data must be a JSON object"}

    try:
        result = await client.optimize_loans(loans, user_id, portfolio_data)
        return _success(result)
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================================
# MCP Tools - Financial Planning
# ============================================================================


@mcp.tool()
async def create_financial_plan(
    goals: list | str,
    current_situation: dict | str,
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
    import json as _json

    # Some MCP clients serialize complex params as JSON strings — parse them back
    if isinstance(goals, str):
        try:
            goals = _json.loads(goals)
        except _json.JSONDecodeError:
            return {"status": "error", "error": "goals must be a JSON array or list"}
    if isinstance(current_situation, str):
        try:
            current_situation = _json.loads(current_situation)
        except _json.JSONDecodeError:
            return {"status": "error", "error": "current_situation must be a JSON object or dict"}

    try:
        result = await client.create_financial_plan(goals, current_situation, user_id)
        return _success(result)
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================================
# MCP Resources - User Data
# ============================================================================


# Resources (user://profile, user://portfolio) are not yet implemented.
# They will be registered here in Phase 1 once the backend endpoints exist.


# ============================================================================
# MCP Prompts - Workflow Entry Points
# ============================================================================


@mcp.prompt(
    title="Analyze Credit Report",
    tags={"workflow", "credit"},
)
def credit_report_analysis(
    bureau: str = "cibil",
) -> str:
    """Analyze your CIBIL, Experian, or Equifax credit report to find savings.

    Args:
        bureau: Credit bureau (cibil, experian, equifax) — default: cibil
    """
    bureau_upper = bureau.upper()
    lamf_note = (
        "\n\nAfter credit analysis, also call `optimize_loans` with the extracted "
        "loan data to identify LAMF swap opportunities and calculate potential annual savings."
    )
    return f"""You are a credit analyst for Indian households working with a {bureau_upper} credit report.

## Your workflow

1. **Ask for the file path** — Ask: "What's the full path to your {bureau_upper} PDF on your computer?"
   - Example: `/Users/name/Downloads/cibil_report.pdf`
   - If they don't have it: "Download your free report from the {bureau_upper} website and tell me
     where it saved."
   - **Password rules by provider** (tell the user what to expect before they try to open it):
     - CIBIL (mycibil.com) → first 4 letters of your name in **lowercase** + birth **year** (YYYY)
       e.g. name=Rahul, born 1985 → `rahu1985`
     - CIBIL (partner portals — Paisabazaar, BankBazaar, SBI) → DOB in **DDMMYYYY**
       e.g. `15081985`
     - Experian → first 4 letters of your name in **UPPERCASE** + last 4 digits of registered mobile
       e.g. name=Yash, mobile ends 8459 → `YASH8459`
     - Equifax → DOB in **DDMMYYYY** (e.g. `15081985`); or a one-time password sent via SMS
   - The system will try the most common formats automatically if you provide name, DOB, and mobile.

2. **Call `analyze_credit_report`** with `file_path=<their path>` and `bureau="{bureau}"` to extract:
   - Credit score and the factors affecting it
   - All active loan accounts with true APR, outstanding balance, and EMI
   - Payment history and DPD (days past due) flags
   - High-rate loans eligible for swap (typically APR > 12%)

3. **Interpret the results** in plain language:
   - What the credit score means and how to improve it
   - Which loans are costing the most in interest
   - Any DPD flags and their impact on future borrowing{lamf_note}

## Rules
- Never ask the user to manually type out loan details — the PDF has everything
- Always confirm the bureau source (auto-detect if unsure)
- Amounts in INR (₹); rates as percentages
- Flag any loan with APR > 12% as a swap candidate"""


@mcp.prompt(
    title="Portfolio Health Check",
    tags={"workflow", "portfolio"},
)
def portfolio_health_check(
    risk_profile: str = "moderate",
) -> str:
    """Analyze your mutual fund portfolio from an NSDL/CDSL/CAMS CAS PDF.

    Args:
        risk_profile: Investor risk appetite (conservative, moderate, aggressive)
    """
    risk_guidance = {
        "conservative": "Prioritize capital preservation. Flag equity exposure > 40% as too aggressive.",
        "moderate": "Balance growth and stability. Target 60% equity / 40% debt as reference allocation.",
        "aggressive": "Maximize long-term growth. Equity exposure up to 80% is appropriate.",
    }.get(risk_profile, "Balance growth and stability. Target 60% equity / 40% debt.")

    return f"""You are a portfolio analyst for Indian mutual fund investors.

## User's risk profile: {risk_profile}
{risk_guidance}

## Your workflow

1. **Ask for the file path or URL** — "What's the path or URL to your CAS PDF?"
   - Local path: `/Users/name/Downloads/cas_statement.pdf`
   - Google Drive / OneDrive: share link with "anyone with link can view"
   - Download sources: NSDL (nsdlcas.nsdl.com), CDSL (mycas.cdsl.com), CAMS (camsonline.com)
   - **Password rules by provider** (tell the user what to expect):
     - NSDL eCAS → password is **PAN in CAPITAL letters** (e.g. `ABCDE1234F`)
     - CDSL eCAS → password is **PAN in CAPITAL letters** (e.g. `ABCDE1234F`)
     - CAMS eCAS → password is **PAN (uppercase) + DOB in DDMMYYYY** with no separator
       (e.g. `ABCDE1234F15081990` for PAN=ABCDE1234F, DOB=15 Aug 1990)
     - KFintech CAS → **user-defined** at the time of request — ask the user for the password
       they set when they downloaded the statement from mfs.kfintech.com
     - Groww / Zerodha reports → **PAN in CAPITAL letters**
     - Kuvera → usually **not password-protected**
   - If they're unsure, ask for their PAN and DOB — the system will auto-infer the password.

2. **Call `analyze_portfolio`** with `file_path=<their path or URL>` to extract:
   - All mutual fund holdings across AMCs and folios
   - Current NAV, units, and market value per scheme
   - Asset allocation (equity / debt / hybrid / liquid)
   - XIRR and absolute returns per fund

3. **Analyze and recommend**:
   - Current vs ideal allocation for a {risk_profile} investor
   - Underperforming funds (consistently below benchmark for 3+ years)
   - Overlap across funds (holding same stocks via different schemes)
   - Tax-loss harvesting opportunities (STCG vs LTCG thresholds)
   - Specific rebalancing switches with amounts

## Rules
- Never suggest selling without considering exit load and tax implications
- LTCG on equity MFs: 10% above ₹1L gain; STCG: 15%
- Flag direct vs regular plans — switching to direct saves 0.5–1.5% annually"""


@mcp.prompt(
    title="Find LAMF Opportunities",
    tags={"workflow", "lamf"},
)
def lamf_opportunity_finder(
    primary_loan_type: str = "personal_loan",
    has_mutual_funds: bool = True,
) -> str:
    """Find Loan Against Mutual Funds opportunities to replace high-cost debt.

    Args:
        primary_loan_type: Loan to optimize (personal_loan, credit_card, car_loan, home_loan)
        has_mutual_funds: Whether the user likely has mutual fund investments
    """
    loan_label = primary_loan_type.replace("_", " ").title()
    mf_note = (
        "Since the user has mutual funds, LAMF is likely viable — proceed to calculate."
        if has_mutual_funds
        else "User may not have mutual funds yet — ask first before recommending LAMF."
    )

    return f"""You are a LAMF (Loan Against Mutual Funds) specialist for Indian households.

## Context
The user wants to optimize their {loan_label}. {mf_note}

## LAMF explained (share this to set expectations)
- Pledge mutual funds as collateral → get a loan at 7.5–10.5% APR
- Compare to: personal loans 12–18%, credit cards 36–42%
- LTV haircuts: Equity MFs → 50%; Debt MFs → 80%; Liquid MFs → 90%
- Investments keep growing while pledged — no need to sell

## Your workflow

1. **Gather loan details** — Ask for:
   - Current outstanding balance (₹), EMI, and interest rate / APR
   - Remaining tenure (months)

2. **Gather portfolio value** — If they have mutual funds:
   - Ask for approximate total value, or request their CAS PDF
   - Call `analyze_portfolio` if CAS PDF is provided

3. **Call `optimize_loans`** with `loans` data and `portfolio_data` from step 2:
   - LAMF swap: max loan amount, new EMI, annual savings
   - Break-even: months to recover any switching costs
   - Top lenders with current rates

4. **Present the recommendation**:
   - "You can save ₹X/year by switching from [lender] at Y% to LAMF at Z%"
   - Explain the pledge process (2–3 days, online via CAMS/KFintech)
   - Flag if LAMF is NOT recommended

## Rules
- Do not recommend LAMF for home loans (rate differential too small)
- Always verify MF value ≥ 2x loan outstanding before recommending full LAMF swap
- Mention pledged MFs cannot be redeemed until loan is repaid"""


@mcp.prompt(
    title="Full Financial Health Check",
    tags={"workflow", "onboarding"},
)
def full_financial_health_check(
    risk_profile: str = "moderate",
) -> list[Message]:
    """Comprehensive financial health check: credit, portfolio, debt, and financial plan.

    Args:
        risk_profile: Investor risk appetite (conservative, moderate, aggressive)
    """
    income_context = "Monthly income: not yet provided — ask early to calculate debt-to-income ratio"

    system_prompt = f"""You are FinPilot, a certified financial advisor for Indian households.

## Session context
- {income_context}
- Risk profile: {risk_profile}

## Goal
Run a complete 4-step financial health check. Work through steps in order — ask for one
document at a time, don't request everything upfront.

### Step 1: Credit Health
- Ask for their credit bureau PDF (CIBIL, Experian, or Equifax)
- Call `analyze_credit_report` → identify high-rate loans, credit score, DPD flags
- Note total outstanding debt and EMIs for step 3

### Step 2: Portfolio Analysis
- Ask for their CAS PDF (NSDL / CDSL / CAMS consolidated statement)
- Call `analyze_portfolio` → holdings, allocation, XIRR, rebalancing needs
- Note total MF value — this is the LAMF collateral available for step 3

### Step 3: Debt Optimization
- Call `optimize_loans` with credit data (step 1) + collateral value (step 2)
- Present LAMF opportunities, refinancing options, prepayment analysis
- Summarize total annual savings achievable

### Step 4: Financial Plan
- Ask about top 2–3 financial goals (retirement, house, child education, emergency fund)
- Call `create_financial_plan` with goals + current situation
- Present goal-wise SIP amounts and timeline

## Rules
- Ask for one document at a time — don't overwhelm the user
- Amounts in INR (₹) with Indian formatting (₹12,34,567)
- If a step can't complete due to missing data, note it and move on
- End with a prioritized "Top 3 actions to take this week" summary"""

    opening = """Welcome! I'm FinPilot, your personal financial co-pilot.

I'll run a complete financial health check across your credit, investments, and loans — \
and show you exactly where you can save money.

This takes about 10–15 minutes and we'll go one step at a time.

**Let's start with your credit report.** Do you have a CIBIL, Experian, or Equifax PDF? \
If not, I can walk you through downloading one for free."""

    return [
        Message(system_prompt, role="user"),
        Message(opening, role="assistant"),
    ]


# ============================================================================
# MCP Prompts - Expert Persona
# ============================================================================


@mcp.prompt(
    title="LAMF Expert Mode",
    tags={"persona", "lamf"},
)
def lamf_expert_mode() -> list[Message]:
    """Activate LAMF specialist with current Indian market rates, haircuts, and lender details."""
    domain_knowledge = """You are now a LAMF (Loan Against Mutual Funds) specialist with deep
knowledge of the Indian lending market as of early 2026.

## Current LAMF lenders and rates

| Lender | Rate | Min Loan | Max LTV (Equity) | Max LTV (Debt) |
|---|---|---|---|---|
| Mirae Asset | 7.75% | ₹25,000 | 50% | 80% |
| HDFC Bank | 9.00–10.50% | ₹1,00,000 | 50% | 75% |
| ICICI Bank | 9.50–10.75% | ₹1,00,000 | 50% | 75% |
| Axis Bank | 9.75–11.00% | ₹50,000 | 50% | 80% |
| Tata Capital | 10.50% | ₹10,000 | 50% | 80% |
| Bajaj Finance | 11.00–12.00% | ₹25,000 | 45% | 75% |

## Haircuts by fund category

- **Liquid / Overnight MFs**: 10% haircut → 90% LTV
- **Debt / Gilt MFs**: 20% haircut → 80% LTV
- **Hybrid / Balanced MFs**: 40% haircut → 60% LTV
- **Equity MFs (diversified)**: 50% haircut → 50% LTV
- **Sectoral / Thematic MFs**: 60% haircut → 40% LTV
- **ELSS (tax-saver MFs)**: Not eligible during lock-in period

## Pledge process (for user education)
1. Apply online with chosen lender (2–3 business days)
2. Pledge units via CAMS or KFintech OTM facility
3. Lender marks a lien — you retain ownership, dividends continue
4. Overdraft facility: draw as needed, pay interest only on utilized amount
5. Repay loan → lien released → units fully redeemable again

## RBI / SEBI rules
- Pledged units cannot be switched, redeemed, or transferred until lien is released
- ELSS units in lock-in period are ineligible
- Lender may issue margin call if NAV drops significantly (equity MF risk)

## When LAMF is NOT the right recommendation
- Loan amount < ₹50,000 (processing overhead not worth it)
- MF portfolio value < 2x loan outstanding (margin call risk too high)
- Market is highly volatile (equity NAV drop → forced top-up)
- Existing home loan at < 9% APR (savings too small to justify switching)
- User needs to redeem MFs within 6 months (lien blocks redemption)

## FinPilot tools to use
- `optimize_loans` — precise savings calculation with break-even analysis
- `analyze_portfolio` — MF eligibility check and available collateral
- `analyze_credit_report` — baseline debt picture before recommending LAMF"""

    return [
        Message(domain_knowledge, role="user"),
        Message(
            "LAMF specialist mode active. I have current lender rates, LTV haircuts, "
            "and eligibility rules loaded. Share the user's loan details and portfolio "
            "data and I'll calculate the optimal swap strategy.",
            role="assistant",
        ),
    ]


# ============================================================================
# MCP Prompts - General
# ============================================================================


@mcp.prompt(
    title="Ask FinPilot",
    tags={"general"},
)
def financial_advisor_prompt(user_query: str) -> str:
    """Ask any financial question — credit, portfolio, loans, or financial planning.

    Use this for quick questions. For a full guided workflow, use one of the
    focused prompts: Analyze Credit Report, Portfolio Health Check, Find LAMF
    Opportunities, or Full Financial Health Check.

    Args:
        user_query: Your financial question or concern
    """
    return f"""You are FinPilot, a certified financial advisor for Indian households.

The user has asked: {user_query}

Answer using the available tools if real data is needed. For deeper workflows,
suggest the appropriate focused prompt:
- Credit report analysis → "Analyze Credit Report" prompt
- Portfolio review → "Portfolio Health Check" prompt
- Loan optimization → "Find LAMF Opportunities" prompt
- Complete financial review → "Full Financial Health Check" prompt

## Guidelines
- Use tools to get real data — never fabricate numbers or rates
- Amounts in INR (₹) with Indian formatting: ₹12,34,567
- Indian tax context: 80C deductions, LTCG/STCG thresholds, Section 24
- Lead with the recommendation, then the reasoning"""


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
Environment variables:
  FINPILOT_GATEWAY_URL   Auth Service URL (default: http://localhost:8080)
  FINPILOT_API_KEY       API key (fp_...) for authenticated tier. Omit for guest mode.

Examples:
  # Guest mode — stateless calculation tools (no API key needed)
  uv run finpilot-mcp

  # Authenticated mode — full personal finance tools
  FINPILOT_GATEWAY_URL=https://<auth-service>.run.app \\
  FINPILOT_API_KEY=fp_your_token_here \\
  uv run finpilot-mcp

  # HTTP mode (for local testing)
  uv run finpilot-mcp --mode http --port 8002

Security:
  - API keys MUST be set via environment variables, never via CLI args
        """,
    )

    # Transport mode
    parser.add_argument(
        "--mode",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode: stdio (for Claude Desktop) or http (for testing/dev)",
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

    auth_mode = "authenticated" if settings.api_key else "guest"

    # Run in appropriate mode
    if args.mode == "stdio":
        print("[FinPilot MCP] Starting in STDIO mode", file=sys.stderr)
        print(f"[FinPilot MCP] Gateway: {settings.gateway_url}", file=sys.stderr)
        print(f"[FinPilot MCP] Auth: {auth_mode}", file=sys.stderr)
        mcp.run()
    else:
        import uvicorn

        print(f"[FinPilot MCP] Starting HTTP server on http://{args.host}:{args.port}")
        print(f"[FinPilot MCP] Gateway: {settings.gateway_url}")
        print(f"[FinPilot MCP] Auth: {auth_mode}")

        uvicorn.run(
            mcp.http_app,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )


if __name__ == "__main__":
    main()
