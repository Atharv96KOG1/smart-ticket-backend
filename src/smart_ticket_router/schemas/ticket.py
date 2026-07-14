from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    BILLING = "Billing"
    TECHNICAL_ISSUE = "Technical Issue"
    ACCOUNT_ACCESS = "Account & Access"
    BUG_REPORT = "Bug Report"
    FEATURE_REQUEST = "Feature Request"
    COMPLAINT = "Complaint"
    GENERAL_INQUIRY = "General Inquiry"
    OUT_OF_SCOPE = "Out of Scope"


class Priority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Team(str, Enum):
    BILLING_TEAM = "Billing Team"
    TECHNICAL_SUPPORT = "Technical Support"
    ACCOUNT_MANAGEMENT = "Account Management"
    ENGINEERING = "Engineering"
    CUSTOMER_SUCCESS = "Customer Success"
    TIER_1_SUPPORT = "Tier-1 Support"


class Confidence(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Issue(BaseModel):
    id: int
    category: Category
    priority: Priority
    assigned_team: Team
    reasoning: str = Field(max_length=200)
    confidence: Confidence | None = None

    model_config = {"extra": "forbid"}


class TicketRoute(BaseModel):
    issues: list[Issue] = Field(min_length=1)
    processing_time_ms: int = 0

    model_config = {"extra": "forbid"}


SAFE_FALLBACK = TicketRoute(
    issues=[
        Issue(
            id=1,
            category=Category.GENERAL_INQUIRY,
            priority=Priority.MEDIUM,
            assigned_team=Team.TIER_1_SUPPORT,
            reasoning="Automatic routing failed validation; escalated to Tier-1 for manual triage.",
            confidence=Confidence.LOW,
        )
    ],
)
