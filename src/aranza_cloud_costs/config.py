from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import ProviderName


class ConfigError(ValueError):
    """Raised when the configuration file or environment is incomplete or invalid."""


_MISSING = object()
_ALLOWED_TOML_OPTIONS = {
    "monitor": {"providers", "currency", "thresholds"},
    "budgets": {"global", "aws", "azure", "gcp", "cloudflare"},
    "aws": {"region"},
    "azure": {"subscription_id"},
    "gcp": {"billing_export_table"},
    "cloudflare": {"month_to_date_cost", "currency"},
    "notifications": {"slack", "telegram", "telegram_chat_id"},
}


def _load_toml(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_file():
        raise ConfigError(f"ARANZA_CLOUD_CONFIG_FILE does not point to a file: {path}.")
    try:
        try:
            import tomllib
        except ModuleNotFoundError:  # Python 3.10
            import tomli as tomllib
        with path.open("rb") as config_file:
            data = tomllib.load(config_file)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Could not read cloud-costs TOML configuration at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("The cloud-costs configuration must contain a TOML table.")
    _validate_toml_options(data)
    return data


def _validate_toml_options(data: Mapping[str, Any]) -> None:
    for section, values in data.items():
        if section not in _ALLOWED_TOML_OPTIONS:
            valid = ", ".join(_ALLOWED_TOML_OPTIONS)
            raise ConfigError(f"Unknown TOML section [{section}]. Valid sections: {valid}.")
        if not isinstance(values, Mapping):
            raise ConfigError(f"[{section}] must be a TOML table.")
        unknown = set(values) - _ALLOWED_TOML_OPTIONS[section]
        if unknown:
            raise ConfigError(
                f"Unknown option(s) in [{section}]: {', '.join(sorted(unknown))}. "
                "See docs/CONFIGURATION.md for supported options."
            )


def _toml_value(data: Mapping[str, Any], section: str, key: str) -> Any:
    table = data.get(section, {})
    if not isinstance(table, Mapping):
        raise ConfigError(f"[{section}] must be a TOML table.")
    return table.get(key, _MISSING)


def _value(env: Mapping[str, str], env_key: str, from_file: Any, default: Any = None) -> Any:
    """Resolve an option. A non-empty environment value always wins over TOML."""
    environment_value = env.get(env_key)
    if environment_value is not None and environment_value.strip():
        return environment_value
    if from_file is not _MISSING:
        return from_file
    return default


def _string(value: Any, key: str) -> str | None:
    if value is None or value is _MISSING:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string.")
    return value.strip() or None


def _decimal(value: Any, key: str) -> Decimal | None:
    if value is None or value is _MISSING:
        return None
    if isinstance(value, bool):
        raise ConfigError(f"{key} must be a number.")
    text = str(value).strip()
    if not text:
        return None
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ConfigError(f"{key} must be a number.") from exc
    if result < 0:
        raise ConfigError(f"{key} cannot be negative.")
    return result


def _boolean(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ConfigError(f"{key} must be true or false.")


def _providers(value: Any) -> tuple[ProviderName, ...]:
    if isinstance(value, str):
        raw_values: Sequence[Any] = value.split(",")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_values = value
    else:
        raise ConfigError("providers must be a comma-separated string or a TOML array.")
    if not raw_values:
        raise ConfigError("providers cannot be empty.")

    selected: list[ProviderName] = []
    for raw in raw_values:
        if not isinstance(raw, str):
            raise ConfigError("Each provider must be a string.")
        normalized = raw.strip().lower()
        try:
            provider = ProviderName(normalized)
        except ValueError as exc:
            valid = ", ".join(item.value for item in ProviderName)
            raise ConfigError(f"Unknown provider '{normalized}'. Valid values: {valid}.") from exc
        if provider not in selected:
            selected.append(provider)
    return tuple(selected)


def _thresholds(value: Any) -> tuple[Decimal, ...]:
    if value is None or value is _MISSING:
        raw_values: Sequence[Any] = ["0.8", "1.0"]
    elif isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_values = value
    else:
        raise ConfigError("thresholds must be a comma-separated string or a TOML array.")

    values: list[Decimal] = []
    for raw in raw_values:
        threshold = _decimal(raw, "thresholds")
        if threshold is None or threshold == 0:
            raise ConfigError("thresholds values must be greater than zero.")
        values.append(threshold)
    if not values:
        raise ConfigError("thresholds cannot be empty.")
    return tuple(sorted(set(values)))


@dataclass(frozen=True)
class CloudCostConfig:
    providers: tuple[ProviderName, ...]
    currency: str
    global_budget: Decimal | None
    provider_budgets: Mapping[ProviderName, Decimal]
    alert_thresholds: tuple[Decimal, ...]
    aws_region: str
    azure_subscription_id: str | None
    gcp_billing_export_table: str | None
    cloudflare_month_to_date_cost: Decimal | None
    cloudflare_currency: str
    slack_enabled: bool
    slack_webhook_url: str | None
    telegram_enabled: bool
    telegram_bot_token: str | None
    telegram_chat_id: str | None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "CloudCostConfig":
        """Load TOML non-secret settings and environment secrets/overrides.

        Set ARANZA_CLOUD_CONFIG_FILE to use TOML. Every ARANZA_CLOUD_* option in
        the environment takes precedence so a deployment can override one value.
        """
        env = os.environ if environ is None else environ
        path = _string(env.get("ARANZA_CLOUD_CONFIG_FILE"), "ARANZA_CLOUD_CONFIG_FILE")
        data = _load_toml(path) if path else {}
        return cls._from_sources(env, data)

    @classmethod
    def from_file(
        cls, path: str | Path, environ: Mapping[str, str] | None = None
    ) -> "CloudCostConfig":
        """Load a TOML configuration directly, useful for application integration tests."""
        env = os.environ if environ is None else environ
        return cls._from_sources(env, _load_toml(str(path)))

    @classmethod
    def _from_sources(cls, env: Mapping[str, str], data: Mapping[str, Any]) -> "CloudCostConfig":
        monitor = lambda key: _toml_value(data, "monitor", key)
        budgets = lambda key: _toml_value(data, "budgets", key)
        aws = lambda key: _toml_value(data, "aws", key)
        azure = lambda key: _toml_value(data, "azure", key)
        gcp = lambda key: _toml_value(data, "gcp", key)
        cloudflare = lambda key: _toml_value(data, "cloudflare", key)
        notifications = lambda key: _toml_value(data, "notifications", key)

        providers_raw = _value(env, "ARANZA_CLOUD_PROVIDERS", monitor("providers"), _MISSING)
        if providers_raw is _MISSING:
            raise ConfigError(
                "Set monitor.providers in cloud-costs.toml or ARANZA_CLOUD_PROVIDERS in the environment."
            )

        provider_budgets: dict[ProviderName, Decimal] = {}
        for provider in ProviderName:
            env_key = f"ARANZA_CLOUD_{provider.value.upper()}_BUDGET"
            amount = _decimal(_value(env, env_key, budgets(provider.value)), env_key)
            if amount is not None:
                provider_budgets[provider] = amount

        slack_webhook_url = _string(env.get("ARANZA_CLOUD_SLACK_WEBHOOK_URL"), "SLACK webhook")
        telegram_bot_token = _string(
            env.get("ARANZA_CLOUD_TELEGRAM_BOT_TOKEN"), "TELEGRAM bot token"
        )
        telegram_chat_id = _string(
            _value(env, "ARANZA_CLOUD_TELEGRAM_CHAT_ID", notifications("telegram_chat_id")),
            "telegram_chat_id",
        )
        slack_enabled = _boolean(
            _value(env, "ARANZA_CLOUD_SLACK_ENABLED", notifications("slack"), bool(slack_webhook_url)),
            "notifications.slack",
        )
        telegram_enabled = _boolean(
            _value(
                env,
                "ARANZA_CLOUD_TELEGRAM_ENABLED",
                notifications("telegram"),
                bool(telegram_bot_token or telegram_chat_id),
            ),
            "notifications.telegram",
        )

        config = cls(
            providers=_providers(providers_raw),
            currency=(
                _string(_value(env, "ARANZA_CLOUD_CURRENCY", monitor("currency"), "USD"), "currency")
                or "USD"
            ).upper(),
            global_budget=_decimal(
                _value(env, "ARANZA_CLOUD_BUDGET", budgets("global")), "ARANZA_CLOUD_BUDGET"
            ),
            provider_budgets=provider_budgets,
            alert_thresholds=_thresholds(
                _value(env, "ARANZA_CLOUD_ALERT_THRESHOLDS", monitor("thresholds"))
            ),
            aws_region=_string(
                _value(env, "ARANZA_CLOUD_AWS_REGION", aws("region"), "us-east-1"), "aws.region"
            )
            or "us-east-1",
            azure_subscription_id=_string(
                _value(env, "ARANZA_CLOUD_AZURE_SUBSCRIPTION_ID", azure("subscription_id")),
                "azure.subscription_id",
            ),
            gcp_billing_export_table=_string(
                _value(env, "ARANZA_CLOUD_GCP_BILLING_EXPORT_TABLE", gcp("billing_export_table")),
                "gcp.billing_export_table",
            ),
            cloudflare_month_to_date_cost=_decimal(
                _value(
                    env,
                    "ARANZA_CLOUD_CLOUDFLARE_MONTH_TO_DATE_COST",
                    cloudflare("month_to_date_cost"),
                ),
                "cloudflare.month_to_date_cost",
            ),
            cloudflare_currency=(
                _string(
                    _value(env, "ARANZA_CLOUD_CLOUDFLARE_CURRENCY", cloudflare("currency"), "USD"),
                    "cloudflare.currency",
                )
                or "USD"
            ).upper(),
            slack_enabled=slack_enabled,
            slack_webhook_url=slack_webhook_url,
            telegram_enabled=telegram_enabled,
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id,
        )
        config.validate_selected_providers()
        return config

    def validate_selected_providers(self) -> None:
        if ProviderName.AZURE in self.providers and not self.azure_subscription_id:
            raise ConfigError("azure.subscription_id is required for Azure.")
        if ProviderName.GCP in self.providers and not self.gcp_billing_export_table:
            raise ConfigError("gcp.billing_export_table is required for GCP.")
        if ProviderName.CLOUDFLARE in self.providers and self.cloudflare_month_to_date_cost is None:
            raise ConfigError(
                "cloudflare.month_to_date_cost is required for Cloudflare. "
                "Cloudflare has no authoritative month-to-date charge API."
            )
        if self.slack_enabled and not self.slack_webhook_url:
            raise ConfigError("ARANZA_CLOUD_SLACK_WEBHOOK_URL is required when notifications.slack is true.")
        if self.telegram_enabled and not (self.telegram_bot_token and self.telegram_chat_id):
            raise ConfigError(
                "ARANZA_CLOUD_TELEGRAM_BOT_TOKEN and notifications.telegram_chat_id "
                "are required when notifications.telegram is true."
            )

    def budget_for(self, provider: ProviderName) -> Decimal | None:
        return self.provider_budgets.get(provider, self.global_budget)
