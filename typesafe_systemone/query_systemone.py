"""Query decision models with the TypeSafe System One API on Databricks.

The System One route on Unity AI Gateway evaluates questions against a piece of
content (the "state") and returns structured answers:

  * noul   - probability (0-1) that a statement is true
  * choice - one label from a set of named criteria, with per-label probabilities
  * score  - probability-weighted position on an ordered scale

Docs: https://docs.databricks.com/aws/en/machine-learning/model-serving/query-systemone-models

Auth is resolved by the Databricks SDK (env vars such as DATABRICKS_HOST /
DATABRICKS_TOKEN, a ~/.databrickscfg profile, or OAuth).

Usage:
    python query_systemone.py
    python query_systemone.py --profile DEFAULT --model system.ai.openjev-qwen35-4b
    python query_systemone.py --message "Where is my package?"
"""

import argparse
import json
import os
import time
from pathlib import Path

import requests
from databricks.sdk.core import Config

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs from .env without overriding existing env vars."""
    if not path.is_file():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)

DEFAULT_MODEL = "system.ai.openjev-qwen35-4b"

SUPPORT_TRIAGE_QUESTIONS = {
    "is_billing": {
        "type": "noul",
        "instructions": "Is this a billing-related request?",
        "criteria": {
            "true": "The message concerns a charge, payment, invoice, or refund.",
            "false": "The message does not concern billing.",
        },
    },
    "intent": {
        "type": "choice",
        "instructions": "Which intent best matches the message?",
        "criteria": {
            "refund": "The customer requests a refund.",
            "duplicate_charge": "The customer reports being charged more than once.",
            "order_status": "The customer asks where an order is or when it will arrive.",
            "account": "The customer has a login, password, or account problem.",
            "other": "Another request.",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgent is the request?",
        "criteria": ["Can wait", "Needs attention soon", "Urgent"],
    },
}

SYSTEMONE_PATH = "/ai-gateway/typesafe/v1/systemone"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--message",
        default="Where is my package?",
        help="Support message to evaluate as System One state.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Fully qualified Unity Catalog model service name.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Optional Databricks CLI profile (otherwise uses DATABRICKS_HOST/TOKEN).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds.",
    )
    return parser.parse_args()


def query_systemone(host: str, token: str, model: str, message: str, timeout: float) -> dict:
    url = host.rstrip("/") + SYSTEMONE_PATH
    payload = {
        "model": model,
        "state": {"message": message, "channel": "support"},
        "questions": SUPPORT_TRIAGE_QUESTIONS,
    }
    started = time.perf_counter()
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    if not response.ok:
        raise SystemExit(
            f"System One request failed ({response.status_code}): {json.dumps(body, indent=2)}"
        )
    body["_elapsed_ms"] = round(elapsed_ms, 1)
    return body


def main() -> None:
    load_env_file(ENV_FILE)
    args = parse_args()
    config = Config(profile=args.profile) if args.profile else Config()
    host = config.host
    token = config.token
    if not host or not token:
        raise SystemExit(
            "Missing Databricks auth. Set DATABRICKS_HOST and DATABRICKS_TOKEN, or pass --profile."
        )

    result = query_systemone(host, token, args.model, args.message, args.timeout)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
