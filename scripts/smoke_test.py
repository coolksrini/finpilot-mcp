"""FinPilot MCP smoke test — drives the server exactly like an MCP client.

Covers connectivity AND real tool executions (LLM extraction, portfolio
analysis, loan optimization, financial plan) through the deployed gateway.

Run against a local checkout:
    uv run python scripts/smoke_test.py

Run as an end user would (installs from public GitHub, spawns over stdio):
    SMOKE_SPAWN="uvx --from git+https://github.com/coolksrini/finpilot-mcp finpilot-mcp" \
        uv run python scripts/smoke_test.py

Environment:
    FINPILOT_GATEWAY_URL  gateway to proxy to (default: dev)
    SMOKE_SPAWN           command used to spawn the server (default: uv run finpilot-mcp)
    SMOKE_CREDIT_PDF      path to a credit report PDF for the full extraction run
                          (optional — costs one real LLM extraction, ~60s;
                          use a SYNTHETIC fixture, never a real person's report)
    SMOKE_CAS_PDF         path to a CAS PDF for portfolio-from-file (optional)
    SMOKE_CAS_PASSWORD    password for the CAS PDF if protected (optional)
"""

import asyncio
import json
import os
import shlex
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

EXPECTED_TOOLS = {
    "analyze_credit_report",
    "get_credit_health",
    "analyze_portfolio",
    "optimize_loans",
    "create_financial_plan",
}

DEFAULT_GATEWAY = "https://auth-service-dev-k3pxxft6eq-el.a.run.app"

SAMPLE_HOLDINGS = {
    "holdings": [
        {
            "scheme": "Parag Parikh Flexi Cap Fund - Direct Growth",
            "amc": "PPFAS Mutual Fund",
            "units": 450.5,
            "nav": 82.10,
            "value": 36986.05,
            "category": "equity",
        },
        {
            "scheme": "HDFC Corporate Bond Fund - Direct Growth",
            "amc": "HDFC Mutual Fund",
            "units": 1200.0,
            "nav": 31.55,
            "value": 37860.00,
            "category": "debt",
        },
    ]
}

SAMPLE_LOANS = [
    {
        "loan_type": "personal",
        "current_outstanding": 350000,
        "interest_rate": 16.5,
        "emi_amount": 12000,
    },
    {
        "loan_type": "credit_card",
        "current_outstanding": 80000,
        "interest_rate": 36.0,
        "emi_amount": 8000,
    },
]


def _text(result) -> str:
    return result.content[0].text if result.content else ""


def _parse(result) -> dict:
    try:
        return json.loads(_text(result))
    except json.JSONDecodeError:
        return {"_raw": _text(result)[:300]}


async def main() -> int:
    spawn = shlex.split(os.environ.get("SMOKE_SPAWN", "uv run finpilot-mcp"))
    gateway = os.environ.get("FINPILOT_GATEWAY_URL", DEFAULT_GATEWAY)
    credit_pdf = os.environ.get("SMOKE_CREDIT_PDF")
    cas_pdf = os.environ.get("SMOKE_CAS_PDF")

    transport = StdioTransport(
        command=spawn[0],
        args=spawn[1:],
        env={**os.environ, "FINPILOT_GATEWAY_URL": gateway},
    )

    async with Client(transport) as client:
        # ── connectivity ────────────────────────────────────────────────
        tools = {t.name for t in await client.list_tools()}
        missing = EXPECTED_TOOLS - tools
        assert not missing, f"missing tools: {missing}"
        print(f"✓ tools ({len(tools)}): {sorted(tools)}")

        prompts = await client.list_prompts()
        assert len(prompts) >= 6, f"expected >=6 prompts, got {len(prompts)}"
        print(f"✓ prompts: {len(prompts)}")

        # ── real run: portfolio analysis from inline holdings ───────────
        result = _parse(
            await client.call_tool("analyze_portfolio", {"portfolio_data": SAMPLE_HOLDINGS})
        )
        assert result.get("status") == "success", f"analyze_portfolio failed: {result}"
        print("✓ analyze_portfolio (inline holdings) → success")

        # ── real run: loan optimization against the portfolio ───────────
        result = _parse(
            await client.call_tool(
                "optimize_loans",
                {"loans": SAMPLE_LOANS, "portfolio_data": SAMPLE_HOLDINGS},
            )
        )
        assert result.get("status") == "success", f"optimize_loans failed: {result}"
        print("✓ optimize_loans (2 loans vs portfolio) → success")

        # ── real run: financial plan ─────────────────────────────────────
        result = _parse(
            await client.call_tool(
                "create_financial_plan",
                {
                    "goals": ["clear high-interest debt in 18 months", "build 6-month emergency fund"],
                    "current_situation": {
                        "monthly_income": 150000,
                        "monthly_expenses": 90000,
                        "loans": SAMPLE_LOANS,
                        "investments": SAMPLE_HOLDINGS,
                    },
                },
            )
        )
        assert result.get("status") == "success", f"create_financial_plan failed: {result}"
        print("✓ create_financial_plan (2 goals) → success")

        # ── real run: full credit extraction (opt-in, costs an LLM call) ─
        if credit_pdf:
            print(f"… analyze_credit_report({os.path.basename(credit_pdf)}) — real extraction, ~60s")
            result = _parse(
                await client.call_tool("analyze_credit_report", {"file_path": credit_pdf})
            )
            assert result.get("status") == "success", f"analyze_credit_report failed: {result}"
            data = result.get("data", {})
            assert data.get("credit_score"), f"no credit_score: {list(data.keys())[:10]}"
            assert data.get("loan_accounts"), "no loan_accounts in extraction"
            print(
                f"✓ analyze_credit_report → score {data.get('credit_score')}, "
                f"{len(data.get('loan_accounts', []))} loans, "
                f"cache={data.get('_metadata', {}).get('cache_status')}"
            )
        else:
            print("– analyze_credit_report skipped (set SMOKE_CREDIT_PDF to a SYNTHETIC fixture)")

        # ── real run: portfolio from CAS PDF (opt-in) ────────────────────
        if cas_pdf:
            args: dict = {"file_path": cas_pdf}
            if os.environ.get("SMOKE_CAS_PASSWORD"):
                args["password"] = os.environ["SMOKE_CAS_PASSWORD"]
            result = _parse(await client.call_tool("analyze_portfolio", args))
            assert result.get("status") == "success", f"analyze_portfolio(CAS) failed: {result}"
            print("✓ analyze_portfolio (CAS PDF) → success")
        else:
            print("– analyze_portfolio(CAS PDF) skipped (set SMOKE_CAS_PDF to run)")

    print("\nSMOKE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
