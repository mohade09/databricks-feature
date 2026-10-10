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
import time

import requests
from databricks.sdk.core import Config

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
