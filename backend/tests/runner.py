import asyncio
import os
import sys
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agent import agent_instance

from app.schemas import TicketRequest, TicketStatus
from app.database import get_ticket_by_idempotency, save_ticket_and_logs


async def run_all_tests():
    print("==================================================")
    print("RUNNING B2B AI SUPPORT ENGINE VERIFICATION TESTS")
    print("==================================================")
    passed = 0
    total = 0

    # Test 1: Tier Upgrade
    total += 1
    try:
        req = TicketRequest(
            ticket_id="TCK-TEST-001",
            customer_id="ACME-CORP-01",
            subject="Upgrade subscription to Enterprise",
            body="Please upgrade our team to Enterprise tier immediately.",
            idempotency_key="RUNNER-IDEMP-001"
        )
        res, logs = await agent_instance.process_ticket(req)
        assert res.status == TicketStatus.RESOLVED, f"Expected RESOLVED, got {res.status}"
        assert res.confidence_score >= 0.80, f"Expected confidence >= 0.80, got {res.confidence_score}"
        assert len(res.actions_taken) == 1, "Expected 1 action taken"
        assert res.actions_taken[0].tool_name == "update_subscription_tier"
        print(f"PASS [Test 1] Subscription Tier Upgrade -> Status: {res.status.value}, Confidence: {res.confidence_score}")
        passed += 1
    except Exception as e:
        print(f"FAIL [Test 1] Subscription Tier Upgrade: {e}")
        traceback.print_exc()

    # Test 2: Account Balance
    total += 1
    try:
        req = TicketRequest(
            ticket_id="TCK-TEST-002",
            customer_id="NEXUS-TECH-04",
            subject="Check ledger balance",
            body="What is our current balance and are there any overdue invoices?",
            idempotency_key="RUNNER-IDEMP-002"
        )
        res, logs = await agent_instance.process_ticket(req)
        assert res.status == TicketStatus.RESOLVED, f"Expected RESOLVED, got {res.status}"
        assert res.confidence_score >= 0.80, f"Expected confidence >= 0.80, got {res.confidence_score}"
        assert len(res.actions_taken) == 1, "Expected 1 action taken"
        assert res.actions_taken[0].tool_name == "check_account_balance"
        print(f"PASS [Test 2] Account Balance Check -> Status: {res.status.value}, Confidence: {res.confidence_score}")
        passed += 1
    except Exception as e:
        print(f"FAIL [Test 2] Account Balance Check: {e}")
        traceback.print_exc()

    # Test 3: Fallback Mechanism (< 0.80 Confidence)
    total += 1
    try:
        req = TicketRequest(
            ticket_id="TCK-TEST-003",
            customer_id="GLOBAL-LOGISTICS-09",
            subject="Something is weird with our system",
            body="I feel like things are not working right maybe refund?",
            idempotency_key="RUNNER-IDEMP-003"
        )
        res, logs = await agent_instance.process_ticket(req)
        assert res.status == TicketStatus.ESCALATED, f"Expected ESCALATED, got {res.status}"
        assert res.confidence_score < 0.80, f"Expected confidence < 0.80, got {res.confidence_score}"
        assert "escalat" in res.reasoning.lower()
        print(f"PASS [Test 3] Low Confidence Fallback -> Status: {res.status.value}, Confidence: {res.confidence_score}")
        passed += 1
    except Exception as e:
        print(f"FAIL [Test 3] Low Confidence Fallback: {e}")
        traceback.print_exc()

    # Test 4: Idempotency Verification
    total += 1
    try:
        req = TicketRequest(
            ticket_id="TCK-TEST-004",
            customer_id="ACME-CORP-01",
            subject="Upgrade subscription",
            body="Please upgrade our plan",
            idempotency_key="RUNNER-IDEMP-004-UNIQUE"
        )
        # First execution & persistence
        res1, logs1 = await agent_instance.process_ticket(req)
        await save_ticket_and_logs(req, res1, logs1)

        # Second lookup with same key
        cached = await get_ticket_by_idempotency("RUNNER-IDEMP-004-UNIQUE")
        assert cached is not None, "Cached ticket should exist"
        assert cached.cached is True, "Ticket should have cached=True flag"
        assert cached.ticket_id == "TCK-TEST-004"
        print("PASS [Test 4] Idempotency Cache Hit -> Successfully returned cached resolution")
        passed += 1
    except Exception as e:
        print(f"FAIL [Test 4] Idempotency Cache: {e}")
        traceback.print_exc()

    print("==================================================")
    print(f"TEST RESULTS: {passed}/{total} PASSED")
    print("==================================================")
    if passed == total:
        return 0
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(run_all_tests()))
