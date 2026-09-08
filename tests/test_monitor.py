from datetime import date
from decimal import Decimal
import unittest

from aranza_cloud_costs.config import CloudCostConfig
from aranza_cloud_costs.models import CostSnapshot, ProviderName
from aranza_cloud_costs.monitor import CloudCostMonitor
from aranza_cloud_costs.providers.base import CostProvider


class FakeAwsProvider(CostProvider):
    name = ProviderName.AWS

    def fetch_month_to_date_cost(self) -> CostSnapshot:
        return CostSnapshot(
            provider=self.name,
            amount=Decimal("85"),
            currency="USD",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 8),
            source="test",
        )


class FailingAzureProvider(CostProvider):
    name = ProviderName.AZURE

    def fetch_month_to_date_cost(self) -> CostSnapshot:
        raise RuntimeError("credential rejected")


class CloudCostMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = CloudCostConfig.from_env(
            {
                "ARANZA_CLOUD_PROVIDERS": "aws",
                "ARANZA_CLOUD_BUDGET": "100",
                "ARANZA_CLOUD_ALERT_THRESHOLDS": "0.8,1",
            }
        )

    def test_creates_alert_for_crossed_threshold_only(self) -> None:
        report = CloudCostMonitor(self.config, providers=[FakeAwsProvider()]).check(notify=False)
        self.assertEqual(len(report.alerts), 1)
        self.assertEqual(report.alerts[0].threshold, Decimal("0.8"))
        self.assertEqual(report.alerts[0].utilization, Decimal("0.85"))

    def test_continues_after_provider_error(self) -> None:
        report = CloudCostMonitor(
            self.config, providers=[FailingAzureProvider(), FakeAwsProvider()]
        ).check(notify=False)
        self.assertEqual(report.errors[ProviderName.AZURE], "credential rejected")
        self.assertEqual(len(report.snapshots), 1)
