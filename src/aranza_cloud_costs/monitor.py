from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from .config import CloudCostConfig
from .models import Alert, CostSnapshot, MonitorReport, ProviderName
from .notifiers import Notifier, configured_notifiers
from .providers import (
    AwsCostProvider,
    AzureCostProvider,
    CloudflareCostProvider,
    CostProvider,
    GcpCostProvider,
)


def default_providers(config: CloudCostConfig) -> list[CostProvider]:
    factories = {
        ProviderName.AWS: AwsCostProvider,
        ProviderName.AZURE: AzureCostProvider,
        ProviderName.GCP: GcpCostProvider,
        ProviderName.CLOUDFLARE: CloudflareCostProvider,
    }
    return [factories[name](config) for name in config.providers]


class CloudCostMonitor:
    def __init__(
        self,
        config: CloudCostConfig,
        providers: Iterable[CostProvider] | None = None,
        notifiers: Iterable[Notifier] | None = None,
    ) -> None:
        self.config = config
        self.providers = list(providers) if providers is not None else default_providers(config)
        self.notifiers = list(notifiers) if notifiers is not None else configured_notifiers(config)

    @classmethod
    def from_env(cls) -> "CloudCostMonitor":
        return cls(CloudCostConfig.from_env())

    def check(self, notify: bool = True) -> MonitorReport:
        report = MonitorReport(generated_at=datetime.now(timezone.utc))
        for provider in self.providers:
            try:
                snapshot = provider.fetch_month_to_date_cost()
                report.snapshots.append(snapshot)
                report.alerts.extend(self._alerts_for(snapshot))
            except Exception as exc:
                report.errors[provider.name] = str(exc)

        if notify:
            for alert in report.alerts:
                for notifier in self.notifiers:
                    try:
                        notifier.send(alert)
                    except Exception as exc:
                        report.errors[alert.provider] = f"Notification failed: {exc}"
        return report

    def _alerts_for(self, snapshot: CostSnapshot) -> list[Alert]:
        budget = self.config.budget_for(snapshot.provider)
        if budget is None or budget == 0:
            return []
        utilization = snapshot.amount / budget
        return [
            Alert(
                provider=snapshot.provider,
                amount=snapshot.amount,
                budget=budget,
                currency=snapshot.currency,
                threshold=threshold,
                utilization=utilization,
            )
            for threshold in self.config.alert_thresholds
            if utilization >= threshold
        ]
