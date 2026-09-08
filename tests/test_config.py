from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from aranza_cloud_costs.config import CloudCostConfig, ConfigError
from aranza_cloud_costs.models import ProviderName


class CloudCostConfigTests(unittest.TestCase):
    def test_reads_multiple_providers_and_provider_budget(self) -> None:
        config = CloudCostConfig.from_env(
            {
                "ARANZA_CLOUD_PROVIDERS": "aws, gcp, aws",
                "ARANZA_CLOUD_BUDGET": "100",
                "ARANZA_CLOUD_GCP_BILLING_EXPORT_TABLE": "project.dataset.table",
                "ARANZA_CLOUD_AWS_BUDGET": "20",
                "ARANZA_CLOUD_ALERT_THRESHOLDS": "1,0.8",
            }
        )
        self.assertEqual(config.providers, (ProviderName.AWS, ProviderName.GCP))
        self.assertEqual(config.budget_for(ProviderName.AWS), Decimal("20"))
        self.assertEqual(config.budget_for(ProviderName.GCP), Decimal("100"))
        self.assertEqual(config.alert_thresholds, (Decimal("0.8"), Decimal("1")))

    def test_rejects_cloudflare_without_collector_value(self) -> None:
        with self.assertRaises(ConfigError):
            CloudCostConfig.from_env({"ARANZA_CLOUD_PROVIDERS": "cloudflare"})

    def test_requires_both_telegram_values(self) -> None:
        with self.assertRaises(ConfigError):
            CloudCostConfig.from_env(
                {"ARANZA_CLOUD_PROVIDERS": "aws", "ARANZA_CLOUD_TELEGRAM_BOT_TOKEN": "token"}
            )

    def test_loads_non_secret_values_from_toml_and_env_overrides_them(self) -> None:
        content = """
            [monitor]
            providers = ["aws", "gcp"]
            currency = "pen"
            thresholds = [0.75, 1.0]

            [budgets]
            global = 100
            aws = 25

            [gcp]
            billing_export_table = "project.dataset.billing_table"

            [notifications]
            slack = true
            telegram = false
        """
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cloud-costs.toml"
            path.write_text(content)
            config = CloudCostConfig.from_env(
                {
                    "ARANZA_CLOUD_CONFIG_FILE": str(path),
                    "ARANZA_CLOUD_AWS_BUDGET": "30",
                    "ARANZA_CLOUD_SLACK_WEBHOOK_URL": "https://hooks.slack.test/example",
                }
            )

        self.assertEqual(config.providers, (ProviderName.AWS, ProviderName.GCP))
        self.assertEqual(config.currency, "PEN")
        self.assertEqual(config.budget_for(ProviderName.AWS), Decimal("30"))
        self.assertEqual(config.budget_for(ProviderName.GCP), Decimal("100"))
        self.assertEqual(config.alert_thresholds, (Decimal("0.75"), Decimal("1.0")))
        self.assertTrue(config.slack_enabled)
        self.assertFalse(config.telegram_enabled)

    def test_enabled_slack_requires_its_secret(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cloud-costs.toml"
            path.write_text('[monitor]\nproviders = ["aws"]\n\n[notifications]\nslack = true\n')
            with self.assertRaises(ConfigError):
                CloudCostConfig.from_env({"ARANZA_CLOUD_CONFIG_FILE": str(path)})
