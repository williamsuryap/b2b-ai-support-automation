from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class TicketStatus(str, Enum):
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    NEEDS_INFO = "NEEDS_INFO"


class PriorityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ToolCallResult(BaseModel):
    tool_name: str = Field(..., description="Name of the invoked deterministic tool")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Input parameters passed to the tool")
    result: Dict[str, Any] = Field(default_factory=dict, description="Output payload returned by the tool")
    success: bool = Field(..., description="Whether the tool executed without error")
    error: Optional[str] = Field(None, description="Error message if tool execution failed")


class TicketRequest(BaseModel):
    ticket_id: str = Field(..., description="Unique client or external ticket identifier (e.g. TCK-101)")
    customer_id: str = Field(..., description="Enterprise customer or organization identifier")
    customer_email: Optional[str] = Field(None, description="Contact email of customer submitting the ticket")
    subject: str = Field(..., min_length=1, description="Subject line of the support inquiry")
    body: str = Field(..., min_length=1, description="Full description or message body of the support ticket")
    idempotency_key: Optional[str] = Field(
        None,
        description="Unique token for deduplication and idempotency. Defaults to ticket_id if not provided."
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional context such as client tier, region, or tags"
    )

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def set_idempotency_default(cls, v: Optional[str], info) -> Optional[str]:
        # Handled in post-validation or model initialization
        return v


class LLMStructuredOutput(BaseModel):
    """Strict schema expected from LLM reasoning and decision gate."""
    category: str = Field(..., description="Inferred category (e.g. BILLING, SUBSCRIPTION, ACCOUNT, TECHNICAL)")
    priority: PriorityLevel = Field(default=PriorityLevel.MEDIUM, description="Assessed priority level")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in automated resolution (0.0 to 1.0)")
    requires_escalation: bool = Field(..., description="True if human intervention is required or confidence < 0.8")
    reasoning: str = Field(..., description="Chain-of-thought rationale explaining the decision")
    tool_to_call: Optional[str] = Field(None, description="Tool name to call, if applicable")
    tool_args: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Arguments for tool call")
    customer_reply: str = Field(..., description="Drafted customer response message")


class TicketResponse(BaseModel):
    ticket_id: str = Field(..., description="Ticket identifier")
    idempotency_key: str = Field(..., description="Idempotency key associated with this execution")
    status: TicketStatus = Field(..., description="Final processing outcome (RESOLVED, ESCALATED, NEEDS_INFO)")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="System confidence score")
    category: str = Field(..., description="Categorization of the ticket")
    reasoning: str = Field(..., description="Explanation of resolution or escalation trigger")
    actions_taken: List[ToolCallResult] = Field(
        default_factory=list,
        description="Audit trace of all deterministic tools executed"
    )
    customer_reply: str = Field(..., description="Customer-facing reply message")
    latency_ms: int = Field(..., description="Total processing latency in milliseconds")
    cached: bool = Field(default=False, description="True if response was served from idempotent cache")


class AuditLogEntry(BaseModel):
    step_name: str
    status: str
    confidence_score: Optional[float] = None
    latency_ms: int = 0
    input_payload: Optional[Dict[str, Any]] = None
    output_payload: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
