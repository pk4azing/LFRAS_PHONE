from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PlanPolicy:
    name: str
    price_per_year_usd: int
    max_vendors_customers: Optional[int]  # None = unlimited
    max_internal_users: Optional[int]  # None = unlimited (EAD + EVS)
    languages: int
    integrations: str  # "none" | "basic" | "advanced"
    support: str  # "email" | "standard" | "priority"
    storage: str
    features: list[str]
    notes: str = ""


PLAN_POLICIES = {
    "ENTERPRISE": PlanPolicy(
        name="Enterprise",
        price_per_year_usd=9999,
        max_vendors_customers=None,
        max_internal_users=None,
        languages=13,
        integrations="advanced",
        support="priority",
        storage="256-bit encrypted cloud storage",
        features=[
            "Unlimited vendors/customers/users",
            "Unlimited document types & storage",
            "Advanced compliance tracking & audit management",
            "Customizable workflows & automated document requests",
            "Multi-language support (13)",
            "Integrations: Microsoft 365, Salesforce, etc.",
            "Priority support with dedicated account manager",
            "Comprehensive training & onboarding",
            "Real-time analytics & reporting dashboards",
        ],
        notes="Full access to all features.",
    ),
    "PROFESSIONAL": PlanPolicy(
        name="Professional",
        price_per_year_usd=8888,
        max_vendors_customers=500,
        max_internal_users=None,
        languages=5,
        integrations="basic",
        support="standard",
        storage="256-bit encrypted cloud storage",
        features=[
            "Up to 500 vendors/customers",
            "Unlimited internal users",
            "Standard compliance tracking & audit tools",
            "Automated document requests with email notifications",
            "Multi-language support (5)",
            "Basic integrations (e.g., Microsoft 365)",
            "Standard support (business hours)",
            "Standard training & onboarding resources",
            "Basic analytics & reporting tools",
        ],
        notes="Language limit: 5. No dedicated account manager.",
    ),
    "ESSENTIALS": PlanPolicy(
        name="Essentials",
        price_per_year_usd=7777,
        max_vendors_customers=100,
        max_internal_users=10,
        languages=1,
        integrations="none",
        support="email",
        storage="256-bit encrypted cloud storage",
        features=[
            "Up to 100 vendors/customers",
            "Up to 10 internal users",
            "Basic compliance tracking & document management",
            "Manual document requests",
            "Single-language (English)",
            "No third‑party integrations",
            "Email‑only support",
            "Self‑service training",
            "Limited analytics (document status only)",
        ],
        notes="Basic analytics; no integrations.",
    ),
}


def get_policy(plan_code: str) -> PlanPolicy:
    return PLAN_POLICIES[plan_code]
