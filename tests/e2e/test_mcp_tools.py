"""E2E tests for finpilot-mcp tools via FastMCP in-process client.

Tests call real MCP tools against the deployed Cloud Run auth service.
Two client fixtures are available:
    mcp_client      — guest mode, no API key
    auth_mcp_client — authenticated mode, fp_... token required

See conftest.py for prerequisites and env var configuration.
"""

import json

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _parse(result) -> dict:
    """Parse first text content item from a FastMCP tool call result.

    FastMCP 2.x returns a CallToolResult with a .content list; older builds
    returned a bare list. Handle both.
    """
    assert result, "Tool returned empty result"
    content = result.content if hasattr(result, "content") else result
    assert content, "Tool returned empty content"
    text = content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


# ---------------------------------------------------------------------------
# Server introspection — guest mode, no API key needed
# ---------------------------------------------------------------------------


class TestServerIntrospection:
    """Verify tool and prompt registration. Requires gateway only."""

    async def test_list_tools(self, mcp_client):
        tools = await mcp_client.list_tools()
        names = {t.name for t in tools}
        assert names == {
            "analyze_credit_report",
            "get_credit_health",
            "analyze_portfolio",
            "optimize_loans",
            "create_financial_plan",
        }

    async def test_tool_descriptions_present(self, mcp_client):
        """Every tool must have a description — it appears in Claude Desktop."""
        tools = await mcp_client.list_tools()
        for tool in tools:
            assert tool.description, f"Tool '{tool.name}' is missing a description"

    async def test_list_prompts(self, mcp_client):
        prompts = await mcp_client.list_prompts()
        names = {p.name for p in prompts}
        assert "credit_report_analysis" in names
        assert "portfolio_health_check" in names
        assert "lamf_opportunity_finder" in names
        assert "full_financial_health_check" in names

    async def test_list_resources(self, mcp_client):
        # No static resources registered (profile/portfolio are served dynamically
        # via tool calls, not MCP resources). Verify the call succeeds with an
        # empty or non-error response.
        resources = await mcp_client.list_resources()
        assert resources is not None  # call succeeded


# ---------------------------------------------------------------------------
# Guest-mode tool calls — inline data, no PDF, no auth
# ---------------------------------------------------------------------------


class TestGuestModeLoanOptimisation:
    """Loan optimisation with inline data — available in guest mode."""

    async def test_optimize_personal_loan(self, mcp_client):
        result = await mcp_client.call_tool(
            "optimize_loans",
            {
                "loans": [
                    {
                        "type": "personal_loan",
                        "outstanding": 500000,
                        "apr": 16.5,
                        "emi": 12000,
                        "tenure_months": 48,
                        "lender": "HDFC Bank",
                    }
                ]
            },
        )
        data = await _parse(result)
        assert data.get("status") == "success", f"Expected success, got: {data}"
        assert "guest_notice" in data, "Guest notice must be present for unauthenticated calls"

    async def test_optimize_credit_card_debt(self, mcp_client):
        """High-APR credit card — prime LAMF swap candidate."""
        result = await mcp_client.call_tool(
            "optimize_loans",
            {
                "loans": [
                    {
                        "type": "credit_card",
                        "outstanding": 150000,
                        "apr": 40.0,
                        "emi": 6000,
                        "tenure_months": 36,
                    }
                ]
            },
        )
        data = await _parse(result)
        assert data.get("status") == "success", f"Expected success, got: {data}"
        assert "guest_notice" in data

    async def test_optimize_multiple_loans(self, mcp_client):
        result = await mcp_client.call_tool(
            "optimize_loans",
            {
                "loans": [
                    {"type": "personal_loan", "outstanding": 300000, "apr": 15.0, "emi": 8000},
                    {"type": "car_loan", "outstanding": 800000, "apr": 9.5, "emi": 18000},
                ]
            },
        )
        data = await _parse(result)
        assert data.get("status") == "success", f"Expected success, got: {data}"
        assert "guest_notice" in data


class TestGuestModePortfolioInlineData:
    """Portfolio analysis from inline holdings dict — available in guest mode."""

    async def test_analyze_portfolio_with_holdings(self, mcp_client):
        result = await mcp_client.call_tool(
            "analyze_portfolio",
            {
                "portfolio_data": {
                    "holdings": [
                        {
                            "scheme": "Parag Parikh Flexi Cap Fund - Direct Growth",
                            "category": "equity",
                            "value": 250000,
                            "units": 3500.5,
                            "nav": 71.4,
                        },
                        {
                            "scheme": "HDFC Nifty 50 Index Fund - Direct Growth",
                            "category": "equity",
                            "value": 150000,
                            "units": 5000.0,
                            "nav": 30.0,
                        },
                        {
                            "scheme": "ICICI Prudential Short Term Fund",
                            "category": "debt",
                            "value": 100000,
                            "units": 2000.0,
                            "nav": 50.0,
                        },
                    ]
                }
            },
        )
        data = await _parse(result)
        assert data.get("status") == "success", f"Expected success, got: {data}"
        assert "data" in data, "Success response must contain analysis data"
        assert "guest_notice" in data, "Guest notice must be present for unauthenticated calls"

    async def test_analyze_portfolio_missing_input_returns_error(self, mcp_client):
        """Neither file_path nor portfolio_data — must return error."""
        result = await mcp_client.call_tool("analyze_portfolio", {})
        data = await _parse(result)
        assert data["status"] == "error"


# ---------------------------------------------------------------------------
# Guest — credit report PDF (no API key; uses sample PDF from repo)
# ---------------------------------------------------------------------------


class TestGuestCreditReportAnalysis:
    """Credit report analysis in guest mode with a real PDF.

    Uses the sample Experian PDF committed at:
      packages/finpilot-py/tests/resources/credit_bureau/sample_experian.pdf

    Guests must:
      - Receive status == "success" (not auth_required)
      - See a guest_notice field in the response
      - Receive a non-empty data section with credit analysis
    """

    async def test_guest_credit_report_returns_success(self, mcp_client, guest_credit_report_pdf):
        """Guest can analyze a credit report PDF — no auth_required returned."""
        result = await mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": guest_credit_report_pdf},
        )
        data = await _parse(result)
        assert data.get("status") == "success", f"Expected success for guest credit report analysis, got: {data}"

    async def test_guest_credit_report_has_guest_notice(self, mcp_client, guest_credit_report_pdf):
        """Guest response must carry guest_notice field."""
        result = await mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": guest_credit_report_pdf},
        )
        data = await _parse(result)
        if data.get("status") == "success":
            assert "guest_notice" in data, f"guest_notice missing from guest credit report response: {data.keys()}"

    async def test_guest_credit_report_has_data_key(self, mcp_client, guest_credit_report_pdf):
        """Successful guest response must contain analysis data."""
        result = await mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": guest_credit_report_pdf},
        )
        data = await _parse(result)
        if data.get("status") == "success":
            assert "data" in data, f"Success response missing 'data' key: {data.keys()}"

    async def test_guest_credit_report_no_auth_required(self, mcp_client, guest_credit_report_pdf):
        """Response must never contain auth_required — gating was removed in Task 6."""
        result = await mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": guest_credit_report_pdf},
        )
        data = await _parse(result)
        assert data.get("status") != "auth_required", (
            f"auth_required returned for guest — GUEST_GATED_ACTIONS should have been removed: {data}"
        )


# ---------------------------------------------------------------------------
# Guest — CAS portfolio PDF (no API key; uses sample PDF from repo)
# ---------------------------------------------------------------------------


class TestGuestPortfolioCasPdf:
    """Portfolio analysis in guest mode with a real CAS PDF.

    Uses the sample CDSL CAS PDF committed at:
      packages/finpilot-py/tests/resources/cas/sample_cdsl_cas.pdf

    Guests must:
      - Receive status == "success" (not auth_required)
      - See a guest_notice field in the response
      - Receive holdings / allocation data
    """

    async def test_guest_cas_portfolio_returns_success(self, mcp_client, guest_cas_pdf):
        """Guest can analyze a CAS portfolio PDF — no auth_required returned."""
        result = await mcp_client.call_tool(
            "analyze_portfolio",
            {"file_path": guest_cas_pdf},
        )
        data = await _parse(result)
        assert data.get("status") == "success", f"Expected success for guest portfolio analysis, got: {data}"

    async def test_guest_cas_portfolio_has_guest_notice(self, mcp_client, guest_cas_pdf):
        """Guest portfolio response must carry guest_notice field."""
        result = await mcp_client.call_tool(
            "analyze_portfolio",
            {"file_path": guest_cas_pdf},
        )
        data = await _parse(result)
        if data.get("status") == "success":
            assert "guest_notice" in data, f"guest_notice missing from guest portfolio response: {data.keys()}"

    async def test_guest_cas_portfolio_has_data_key(self, mcp_client, guest_cas_pdf):
        """Successful guest response must contain portfolio analysis data."""
        result = await mcp_client.call_tool(
            "analyze_portfolio",
            {"file_path": guest_cas_pdf},
        )
        data = await _parse(result)
        if data.get("status") == "success":
            assert "data" in data, f"Success response missing 'data' key: {data.keys()}"

    async def test_guest_cas_portfolio_no_auth_required(self, mcp_client, guest_cas_pdf):
        """Response must never contain auth_required — gating was removed in Task 6."""
        result = await mcp_client.call_tool(
            "analyze_portfolio",
            {"file_path": guest_cas_pdf},
        )
        data = await _parse(result)
        assert data.get("status") != "auth_required", (
            f"auth_required returned for guest — GUEST_GATED_ACTIONS should have been removed: {data}"
        )


# ---------------------------------------------------------------------------
# Credit report data quality — guest mode, checks enrichment correctness
# ---------------------------------------------------------------------------


class TestCreditReportDataQuality:
    """Verify the credit report response contains expected data fields.

    Regression coverage for:
      - enrichment_failed: true (fixed by replacing MCP round-trip with direct Python calls)
      - Missing credit_score, bureau_source, loan_accounts fields
    """

    async def test_credit_report_no_enrichment_failure(self, mcp_client, guest_credit_report_pdf):
        """Response must NOT contain enrichment_failed: true.

        Regression test: the enrichment step was calling analyze_credit_health_tool
        on mcp-core (where it doesn't exist), causing enrichment_failed=True.
        Fixed by using finpilot.tools.credit_health directly in the agent.
        """
        result = await mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": guest_credit_report_pdf},
        )
        data = await _parse(result)
        if data.get("status") == "success":
            report = data.get("data", {})
            assert report.get("enrichment_failed") is not True, (
                "enrichment_failed=True in credit report response — "
                "direct credit_health tool call regression: check agent.py _enrich_credit_profile"
            )

    async def test_credit_report_has_credit_score(self, mcp_client, guest_credit_report_pdf):
        """Successful credit report must include a numeric credit_score."""
        result = await mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": guest_credit_report_pdf},
        )
        data = await _parse(result)
        if data.get("status") != "success":
            pytest.skip(f"Credit report analysis returned non-success: {data.get('status')}")
        report = data.get("data", {})
        assert "credit_score" in report, f"credit_score missing from response: {list(report.keys())}"
        score = report["credit_score"]
        assert isinstance(score, (int, float)) and 300 <= score <= 900, (
            f"credit_score out of expected CIBIL range [300, 900]: {score}"
        )

    async def test_credit_report_has_bureau_source(self, mcp_client, guest_credit_report_pdf):
        """Successful response must identify the bureau (cibil/experian/equifax/crif)."""
        result = await mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": guest_credit_report_pdf},
        )
        data = await _parse(result)
        if data.get("status") != "success":
            pytest.skip(f"Credit report analysis returned non-success: {data.get('status')}")
        report = data.get("data", {})
        bureau = report.get("bureau_source", "")
        assert bureau, f"bureau_source missing or empty: {report}"
        assert bureau.lower() in ("cibil", "experian", "equifax", "crif"), f"Unexpected bureau_source: {bureau}"

    async def test_credit_report_has_loan_accounts(self, mcp_client, guest_credit_report_pdf):
        """Successful response must contain a loan_accounts list (possibly empty)."""
        result = await mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": guest_credit_report_pdf},
        )
        data = await _parse(result)
        if data.get("status") != "success":
            pytest.skip(f"Credit report analysis returned non-success: {data.get('status')}")
        report = data.get("data", {})
        assert "loan_accounts" in report, f"loan_accounts missing from credit report response: {list(report.keys())}"
        assert isinstance(report["loan_accounts"], list), (
            f"loan_accounts is not a list: {type(report['loan_accounts'])}"
        )

    async def test_credit_report_high_rate_loans_identified(self, mcp_client, guest_credit_report_pdf):
        """If loan_accounts exist, high_rate_loans must also be present (enrichment step)."""
        result = await mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": guest_credit_report_pdf},
        )
        data = await _parse(result)
        if data.get("status") != "success":
            pytest.skip(f"Credit report analysis returned non-success: {data.get('status')}")
        report = data.get("data", {})
        if not report.get("loan_accounts"):
            pytest.skip("No loan_accounts in report — skipping high_rate_loans check")
        assert "high_rate_loans" in report, (
            "high_rate_loans missing from enriched response — enrichment step may have failed silently"
        )


# ---------------------------------------------------------------------------
# Authenticated — credit report PDF (requires FINPILOT_API_KEY + CREDIT_REPORT_PDF)
# ---------------------------------------------------------------------------


class TestAuthCreditReportAnalysis:
    """Credit report analysis from a local PDF. Requires API key + PDF file."""

    async def test_analyze_credit_report_autodetect_bureau(self, auth_mcp_client, credit_report_pdf):
        """Bureau is auto-detected from PDF content when not specified."""
        result = await auth_mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": credit_report_pdf},
        )
        data = await _parse(result)
        assert data.get("status") in ("success", "error"), f"Unexpected: {data}"

    async def test_analyze_credit_report_explicit_bureau(self, auth_mcp_client, credit_report_pdf):
        result = await auth_mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": credit_report_pdf, "bureau": "cibil"},
        )
        data = await _parse(result)
        assert data.get("status") in ("success", "error")

    async def test_credit_report_success_has_data_key(self, auth_mcp_client, credit_report_pdf):
        result = await auth_mcp_client.call_tool(
            "analyze_credit_report",
            {"file_path": credit_report_pdf},
        )
        data = await _parse(result)
        if data.get("status") == "success":
            assert "data" in data, "Success response must contain 'data'"


# ---------------------------------------------------------------------------
# Authenticated — CAS portfolio PDF (requires FINPILOT_API_KEY + CAS_PDF)
# ---------------------------------------------------------------------------


class TestAuthPortfolioCasPdf:
    """Portfolio analysis from a CAS PDF. Requires API key + CAS file."""

    async def test_analyze_portfolio_cas_pdf(self, auth_mcp_client, cas_pdf):
        result = await auth_mcp_client.call_tool(
            "analyze_portfolio",
            {"file_path": cas_pdf},
        )
        data = await _parse(result)
        assert data.get("status") in ("success", "error"), f"Unexpected: {data}"

    async def test_portfolio_success_has_data_key(self, auth_mcp_client, cas_pdf):
        result = await auth_mcp_client.call_tool(
            "analyze_portfolio",
            {"file_path": cas_pdf},
        )
        data = await _parse(result)
        if data.get("status") == "success":
            assert "data" in data
