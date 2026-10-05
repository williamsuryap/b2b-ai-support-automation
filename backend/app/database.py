"""PostgreSQL database layer using asyncpg connection pool.

Implements:
- Idempotency verification
- Ticket state persistence
- Audit ledger recording
- Graceful in-memory fallback when database is initializing or offline
"""

import json
import logging
from typing import Any, Dict, List, Optional
try:
    import asyncpg
    PoolType = asyncpg.Pool
except ImportError:
    asyncpg = None
    PoolType = Any

from app.config import settings
from app.schemas import AuditLogEntry, TicketRequest, TicketResponse, TicketStatus, ToolCallResult

logger = logging.getLogger("b2b_database")
logger.setLevel(logging.INFO)

_pool: Optional[PoolType] = None
_in_memory_tickets: Dict[str, Dict[str, Any]] = {}
_in_memory_logs: List[Dict[str, Any]] = []


async def init_db_pool():
    """Initializes asyncpg connection pool."""
    global _pool
    if asyncpg is None:
        logger.info("asyncpg not installed in local environment. Operating with in-memory persistence fallback.")
        _pool = None
        return

    try:
        _pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=10.0,
        )
        logger.info("Successfully connected to PostgreSQL connection pool.")
    except Exception as e:
        logger.warning(
            f"Could not connect to PostgreSQL ({e}). Operating with in-memory persistence fallback."
        )
        _pool = None


async def close_db_pool():
    """Closes asyncpg connection pool on application shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        logger.info("PostgreSQL connection pool closed.")


async def get_ticket_by_idempotency(idempotency_key: str) -> Optional[TicketResponse]:
    """Retrieves existing ticket if already processed under this idempotency_key."""
    global _pool
    if _pool:
        try:
            async with _pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT ticket_id, idempotency_key, status, confidence_score,
                           category, resolution_summary, actions_taken, customer_reply,
                           execution_time_ms
                    FROM tickets
                    WHERE idempotency_key = $1
                    """,
                    idempotency_key,
                )
                if row:
                    actions = []
                    raw_actions = row["actions_taken"]
                    if isinstance(raw_actions, str):
                        raw_actions = json.loads(raw_actions)
                    if isinstance(raw_actions, list):
                        for a in raw_actions:
                            actions.append(
                                ToolCallResult(
                                    tool_name=a.get("tool", a.get("tool_name", "unknown")),
                                    parameters=a.get("parameters", {}),
                                    result=a.get("details", a.get("result", {})),
                                    success=(a.get("status") == "SUCCESS" or a.get("success", True)),
                                    error=a.get("error"),
                                )
                            )

                    return TicketResponse(
                        ticket_id=row["ticket_id"],
                        idempotency_key=row["idempotency_key"],
                        status=TicketStatus(row["status"]),
                        confidence_score=float(row["confidence_score"] or 1.0),
                        category=row["category"] or "GENERAL",
                        reasoning=f"Idempotent cached response: {row['resolution_summary']}",
                        actions_taken=actions,
                        customer_reply=row["customer_reply"] or "",
                        latency_ms=row["execution_time_ms"] or 0,
                        cached=True,
                    )
        except Exception as e:
            logger.warning(f"Error querying Postgres for idempotency key '{idempotency_key}': {e}")

    # In-memory lookup fallback
    if idempotency_key in _in_memory_tickets:
        cached_data = _in_memory_tickets[idempotency_key]
        cached_data["cached"] = True
        return TicketResponse(**cached_data)

    return None


async def save_ticket_and_logs(
    request: TicketRequest,
    response: TicketResponse,
    logs: List[AuditLogEntry],
):
    """Persists ticket resolution state and audit logs into PostgreSQL."""
    global _pool

    actions_json = json.dumps([a.model_dump() for a in response.actions_taken])

    if _pool:
        try:
            async with _pool.acquire() as conn:
                async with conn.transaction():
                    # Insert / Update ticket
                    ticket_record = await conn.fetchrow(
                        """
                        INSERT INTO tickets (
                            idempotency_key, ticket_id, customer_id, customer_email,
                            subject, body, category, status, confidence_score,
                            resolution_summary, customer_reply, actions_taken,
                            execution_time_ms
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13
                        )
                        ON CONFLICT (idempotency_key) DO UPDATE SET
                            status = EXCLUDED.status,
                            confidence_score = EXCLUDED.confidence_score,
                            resolution_summary = EXCLUDED.resolution_summary,
                            customer_reply = EXCLUDED.customer_reply,
                            actions_taken = EXCLUDED.actions_taken,
                            execution_time_ms = EXCLUDED.execution_time_ms,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id;
                        """,
                        response.idempotency_key,
                        response.ticket_id,
                        request.customer_id,
                        request.customer_email,
                        request.subject,
                        request.body,
                        response.category,
                        response.status.value,
                        response.confidence_score,
                        response.reasoning,
                        response.customer_reply,
                        actions_json,
                        response.latency_ms,
                    )

                    db_ticket_id = ticket_record["id"] if ticket_record else None

                    # Insert execution audit logs
                    for log in logs:
                        await conn.execute(
                            """
                            INSERT INTO execution_logs (
                                ticket_id, idempotency_key, step_name, status,
                                confidence_score, latency_ms, input_payload,
                                output_payload, error_message
                            ) VALUES (
                                $1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9
                            );
                            """,
                            db_ticket_id,
                            response.idempotency_key,
                            log.step_name,
                            log.status,
                            log.confidence_score,
                            log.latency_ms,
                            json.dumps(log.input_payload) if log.input_payload else None,
                            json.dumps(log.output_payload) if log.output_payload else None,
                            log.error_message,
                        )
            return
        except Exception as e:
            logger.warning(f"Failed to persist ticket to PostgreSQL: {e}. Storing in memory.")

    # In-memory persistence fallback
    _in_memory_tickets[response.idempotency_key] = response.model_dump()
    for log in logs:
        _in_memory_logs.append(log.model_dump())
