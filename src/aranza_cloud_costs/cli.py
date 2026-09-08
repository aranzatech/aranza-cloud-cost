from __future__ import annotations

import argparse
import json

from .config import ConfigError
from .monitor import CloudCostMonitor


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate multi-cloud month-to-date costs and budgets.")
    parser.add_argument("command", choices=["check"], help="Action to execute.")
    parser.add_argument("--no-notify", action="store_true", help="Do not send Slack or Telegram alerts.")
    args = parser.parse_args()

    try:
        report = CloudCostMonitor.from_env().check(notify=not args.no_notify)
    except ConfigError as exc:
        parser.error(str(exc))
    print(json.dumps(report.as_dict(), indent=2))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
