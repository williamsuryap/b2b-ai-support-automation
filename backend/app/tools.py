"""Mock B2B enterprise tools for autonomous ticket resolution.

Includes:
- check_account_balance: Inquires current account ledger balance & invoices.
- update_subscription_tier: Updates billing tier with validation and seat quota.
"""

from datetime import datetime, timezone
from typing import Any, Dict
try:
    from langchain_core.tools import tool
except ImportError:
    # Resilient fallback decorator for standalone/local testing without langchain_core
    def tool(func):
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper.invoke = lambda kwargs: func(**kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper


# Mock in-memory state store for customer accounts
MOCK_ACCOUNTS_DB: Dict[str, Dict[str, Any]] = {
    "ACME-CORP-01": {
        "account_id": "ACME-CORP-01",
        "company_name": "Acme Corporation",
        "current_tier": "Professional",
        "balance_usd": 12500.00,
        "currency": "USD",
        "overdue_invoices_count": 0,
        "overdue_amount_usd": 0.00,
        "credit_limit_usd": 50000.00,
        "billing_cycle": "ANNUAL",
        "seats_allocated": 75,
        "status": "ACTIVE",
    },
    "NEXUS-TECH-04": {
        "account_id": "NEXUS-TECH-04",
        "company_name": "Nexus Technologies",
        "current_tier": "Starter",
        "balance_usd": 4250.00,
        "currency": "USD",
        "overdue_invoices_count": 0,
        "overdue_amount_usd": 0.00,
        "credit_limit_usd": 10000.00,
        "billing_cycle": "MONTHLY",
        "seats_allocated": 15,
        "status": "ACTIVE",
    },
    "GLOBAL-LOGISTICS-09": {
        "account_id": "GLOBAL-LOGISTICS-09",
        "company_name": "Global Logistics Corp",
        "current_tier": "Enterprise",
        "balance_usd": 850.00,
        "currency": "USD",
        "overdue_invoices_count": 1,
        "overdue_amount_usd": 2400.00,
        "credit_limit_usd": 100000.00,
        "billing_cycle": "ANNUAL",
        "seats_allocated": 250,
        "status": "OVERDUE_WARNING",
    },
}

TIER_PRICING: Dict[str, Dict[str, Any]] = {
    "STARTER": {"name": "Starter", "monthly_cost": 49.00, "max_seats": 20, "sla_hours": 24},
    "PROFESSIONAL": {"name": "Professional", "monthly_cost": 199.00, "max_seats": 100, "sla_hours": 8},
    "ENTERPRISE": {"name": "Enterprise", "monthly_cost": 999.00, "max_seats": 1000, "sla_hours": 1},
}


def _get_or_create_account(account_id: str) -> Dict[str, Any]:
    norm_id = account_id.strip().upper()
    if norm_id not in MOCK_ACCOUNTS_DB:
        MOCK_ACCOUNTS_DB[norm_id] = {
            "account_id": norm_id,
            "company_name": f"Enterprise Account {norm_id}",
            "current_tier": "Professional",
            "balance_usd": 5000.00,
            "currency": "USD",
            "overdue_invoices_count": 0,
            "overdue_amount_usd": 0.00,
            "credit_limit_usd": 25000.00,
            "billing_cycle": "MONTHLY",
            "seats_allocated": 25,
            "status": "ACTIVE",
        }
    return MOCK_ACCOUNTS_DB[norm_id]


@tool
def check_account_balance(account_id: str) -> Dict[str, Any]:
    """Retrieve financial ledger and balance details for an enterprise customer account.

    Args:
        account_id: The unique identifier of the customer account (e.g. 'ACME-CORP-01').

    Returns:
        A dictionary containing balance, currency, overdue invoices, and credit limit.
    """
    account = _get_or_create_account(account_id)
    return {
        "success": True,
        "account_id": account["account_id"],
        "company_name": account["company_name"],
        "balance_usd": float(account["balance_usd"]),
        "currency": account["currency"],
        "overdue_invoices_count": account["overdue_invoices_count"],
        "overdue_amount_usd": float(account["overdue_amount_usd"]),
        "credit_limit_usd": float(account["credit_limit_usd"]),
        "status": account["status"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@tool
def update_subscription_tier(account_id: str, new_tier: str) -> Dict[str, Any]:
    """Update or upgrade the subscription tier for an enterprise customer account.

    Args:
        account_id: The unique identifier of the customer account.
        new_tier: Desired tier name ('Starter', 'Professional', or 'Enterprise').

    Returns:
        A dictionary confirming tier update details, effective date, and pricing.
    """
    tier_key = new_tier.strip().upper()
    if tier_key not in TIER_PRICING:
        valid_tiers = list(TIER_PRICING.keys())
        return {
            "success": False,
            "error": f"Invalid tier '{new_tier}'. Supported tiers are: {', '.join(valid_tiers)}.",
        }

    account = _get_or_create_account(account_id)
    previous_tier = account["current_tier"]
    target_tier_meta = TIER_PRICING[tier_key]

    # Apply update to account state
    account["current_tier"] = target_tier_meta["name"]
    account["seats_allocated"] = max(account["seats_allocated"], target_tier_meta["max_seats"] // 2)

    return {
        "success": True,
        "account_id": account["account_id"],
        "previous_tier": previous_tier,
        "new_tier": target_tier_meta["name"],
        "monthly_cost_usd": target_tier_meta["monthly_cost"],
        "max_seats": target_tier_meta["max_seats"],
        "effective_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "confirmation_id": f"TIER-CHG-{int(datetime.now(timezone.utc).timestamp())}",
        "message": f"Successfully updated account '{account['account_id']}' to {target_tier_meta['name']} tier.",
    }


# Exportable list of LangChain tools
AVAILABLE_TOOLS = [check_account_balance, update_subscription_tier]
TOOLS_BY_NAME = {
    "check_account_balance": check_account_balance,
    "update_subscription_tier": update_subscription_tier,
}
