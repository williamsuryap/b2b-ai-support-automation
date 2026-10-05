import pytest
from httpx import AsyncClient, ASGITransport

from app.agent import agent_instance
from app.main import app
from app.schemas import TicketRequest, TicketStatus


@pytest.mark.asyncio
async def test_update_subscription_tier_resolved():
    """Validates subscription tier upgrade executes tool and resolves with confidence >= 0.80."""
    request = TicketRequest(
        ticket_id="TCK-TEST-001",
        customer_id="ACME-CORP-01",
        subject="Upgrade subscription to Enterprise",
        body="Please upgrade our current team account to the Enterprise tier immediately.",
        idempotency_key="TEST-IDEMP-001",
    )

    response, audit_logs = await agent_instance.process_ticket(request)

    assert response.status == TicketStatus.RESOLVED
    assert response.confidence_score >= 0.80
    assert response.category == "SUBSCRIPTION"
    assert len(response.actions_taken) == 1
    action = response.actions_taken[0]
    assert action.tool_name == "update_subscription_tier"
    assert action.success is True
    assert action.result.get("new_tier") == "Enterprise"
    assert "Enterprise" in response.customer_reply
    assert any(log.step_name == "CONFIDENCE_GATEKEEPER" for log in audit_logs)


@pytest.mark.asyncio
async def test_check_account_balance_resolved():
    """Validates account balance inquiry invokes tool and resolves with confidence >= 0.80."""
    request = TicketRequest(
        ticket_id="TCK-TEST-002",
        customer_id="NEXUS-TECH-04",
        subject="Check ledger balance and overdue invoices",
        body="What is our current balance and are there any overdue invoices pending?",
        idempotency_key="TEST-IDEMP-002",
    )

    response, audit_logs = await agent_instance.process_ticket(request)

    assert response.status == TicketStatus.RESOLVED
    assert response.confidence_score >= 0.80
    assert response.category == "BILLING"
    assert len(response.actions_taken) == 1
    action = response.actions_taken[0]
    assert action.tool_name == "check_account_balance"
    assert action.success is True
    assert "balance_usd" in action.result
    assert any(log.step_name == "CONFIDENCE_GATEKEEPER" for log in audit_logs)


@pytest.mark.asyncio
async def test_low_confidence_fallback_escalation():
    """Validates low confidence or ambiguous inquiry gracefully falls back to ESCALATED without crashing."""
    request = TicketRequest(
        ticket_id="TCK-TEST-003",
        customer_id="GLOBAL-LOGISTICS-09",
        subject="Something is weird with our system",
        body="I feel like things are not working right maybe check my thing? We might need a refund.",
        idempotency_key="TEST-IDEMP-003",
    )

    response, audit_logs = await agent_instance.process_ticket(request)

    # Must gracefully escalate without raising exception
    assert response.status == TicketStatus.ESCALATED
    assert response.confidence_score < 0.80
    assert "escalat" in response.reasoning.lower()
    assert "TCK-TEST-003" in response.customer_reply
    assert any(log.step_name == "CONFIDENCE_GATEKEEPER" for log in audit_logs)


@pytest.mark.asyncio
async def test_api_endpoint_and_idempotency():
    """Validates FastAPI /api/v1/process-ticket endpoint and idempotency deduplication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Initial submission
        payload = {
            "ticket_id": "TCK-IDEMP-TEST",
            "customer_id": "ACME-CORP-01",
            "subject": "Upgrade to Enterprise tier",
            "body": "Please upgrade us to Enterprise.",
            "idempotency_key": "IDEMP-KEY-UNIQUE-999",
        }

        res1 = await ac.post("/api/v1/process-ticket", json=payload)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["status"] == "RESOLVED"
        assert data1["cached"] is False

        # Duplicate submission with identical idempotency_key
        res2 = await ac.post("/api/v1/process-ticket", json=payload)
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["status"] == "RESOLVED"
        assert data2["cached"] is True
        assert data2["ticket_id"] == data1["ticket_id"]


@pytest.mark.asyncio
async def test_health_check_endpoint():
    """Validates /health endpoint status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["service"] == "b2b-ai-support-backend"
