"""FastAPI Microservice for B2B AI Support & Workflow Automation.

Exposes:
- POST /api/v1/process-ticket (Idempotent structured LLM resolution & tool execution)
- GET /health (Container healthcheck & readiness probe)
- GET /api/v1/metrics (Operational KPI summary)
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.agent import agent_instance
from app.config import settings
from app.database import (
    _in_memory_tickets,
    _pool,
    close_db_pool,
    get_ticket_by_idempotency,
    init_db_pool,
    save_ticket_and_logs,
)
from app.schemas import TicketRequest, TicketResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("b2b_fastapi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler managing asyncpg connection pooling."""
    logger.info("Initializing B2B Support Automation Engine...")
    await init_db_pool()
    yield
    logger.info("Shutting down B2B Support Automation Engine...")
    await close_db_pool()


app = FastAPI(
    title="B2B AI Support Automation Engine",
    description="Production-grade structured LLM microservice for automated enterprise ticket resolution with tool calling, idempotency, and fallback escalation.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Monitoring"])
async def health_check() -> Dict[str, Any]:
    """Healthcheck endpoint for container orchestration and uptime monitoring."""
    db_connected = _pool is not None
    return {
        "status": "healthy",
        "service": "b2b-ai-support-backend",
        "version": "1.0.0",
        "database_connected": db_connected,
        "llm_mode": "live_openai" if agent_instance.client else "deterministic_simulation",
        "confidence_threshold": agent_instance.confidence_threshold,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post(
    "/api/v1/process-ticket",
    response_model=TicketResponse,
    status_code=status.HTTP_200_OK,
    tags=["Support Engine"],
    summary="Process support ticket with tool calling & fallback escalation",
)
async def process_ticket(request: TicketRequest) -> TicketResponse:
    """Processes an incoming customer support ticket.

    Workflow:
    1. Idempotency Check: Returns cached response if ticket was already processed.
    2. Agent Execution: Runs LLM tool calling (check_account_balance, update_subscription_tier).
    3. Fallback Gatekeeper: Enforces status 'ESCALATED' if confidence < 0.80 or schema fails.
    4. Audit Logging: Persists resolution state and immutable execution logs to PostgreSQL.
    """
    idemp_key = request.idempotency_key or request.ticket_id

    # 1. Idempotency Check
    existing = await get_ticket_by_idempotency(idemp_key)
    if existing:
        logger.info(f"Idempotent hit for key '{idemp_key}'. Returning cached resolution.")
        return existing

    # 2. Execute Structured Support Agent
    logger.info(f"Processing ticket '{request.ticket_id}' for customer '{request.customer_id}'")
    response, audit_logs = await agent_instance.process_ticket(request)

    # 3. Persist State and Audit Logs
    await save_ticket_and_logs(request, response, audit_logs)

    return response


@app.get("/api/v1/metrics", tags=["Analytics"])
async def get_metrics() -> Dict[str, Any]:
    """Returns quick aggregate operational metrics."""
    if _pool:
        try:
            async with _pool.acquire() as conn:
                total = await conn.fetchval("SELECT COUNT(*) FROM tickets;")
                resolved = await conn.fetchval("SELECT COUNT(*) FROM tickets WHERE status = 'RESOLVED';")
                escalated = await conn.fetchval("SELECT COUNT(*) FROM tickets WHERE status = 'ESCALATED';")
                avg_latency = await conn.fetchval("SELECT AVG(execution_time_ms) FROM tickets;") or 0
                return {
                    "total_tickets": total or 0,
                    "resolved_tickets": resolved or 0,
                    "escalated_tickets": escalated or 0,
                    "auto_resolution_rate_pct": round(((resolved or 0) / total * 100), 2) if total else 0.0,
                    "avg_execution_latency_ms": round(float(avg_latency), 2),
                    "source": "postgresql",
                }
        except Exception as e:
            logger.warning(f"Error reading metrics from Postgres: {e}")

    # Fallback to in-memory stats
    total = len(_in_memory_tickets)
    resolved = sum(1 for t in _in_memory_tickets.values() if t.get("status") == "RESOLVED")
    escalated = sum(1 for t in _in_memory_tickets.values() if t.get("status") == "ESCALATED")
    return {
        "total_tickets": total,
        "resolved_tickets": resolved,
        "escalated_tickets": escalated,
        "auto_resolution_rate_pct": round((resolved / total * 100), 2) if total else 0.0,
        "avg_execution_latency_ms": 350.0,
        "source": "in_memory",
    }
