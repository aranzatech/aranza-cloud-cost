from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class ProviderName(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    CLOUDFLARE = "cloudflare"


@dataclass(frozen=True)
class CostSnapshot:
    provider: ProviderName
    amount: Decimal
    currency: str
    period_start: date
    period_end: date
    source: str


@dataclass(frozen=True)
class Alert:
    provider: ProviderName
    amount: Decimal
    budget: Decimal
    currency: str
    threshold: Decimal
    utilization: Decimal

    @property
    def exceeded(self) -> bool:
        return self.utilization >= Decimal("1")


@dataclass
class MonitorReport:
    generated_at: datetime
    snapshots: list[CostSnapshot] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    errors: dict[ProviderName, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "snapshots": [
                {
                    "provider": item.provider.value,
                    "amount": str(item.amount),
                    "currency": item.currency,
                    "period_start": item.period_start.isoformat(),
                    "period_end": item.period_end.isoformat(),
                    "source": item.source,
                }
                for item in self.snapshots
            ],
            "alerts": [
                {
                    "provider": item.provider.value,
                    "amount": str(item.amount),
                    "budget": str(item.budget),
                    "currency": item.currency,
                    "threshold": str(item.threshold),
                    "utilization": str(item.utilization),
                    "exceeded": item.exceeded,
                }
                for item in self.alerts
            ],
            "errors": {provider.value: error for provider, error in self.errors.items()},
        }
