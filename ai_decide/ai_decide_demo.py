# Databricks notebook source
# MAGIC %md
# MAGIC # `ai_decide` demo: fast, structured decisions on governed data
# MAGIC
# MAGIC `ai_decide` is a Databricks AI Function (Beta) backed by a **decision model** instead of a generative LLM.
# MAGIC It checks one or more questions against a piece of text and, for each question, returns one of these:
# MAGIC
# MAGIC | Question `type` | What you get back | Typical use |
# MAGIC |---|---|---|
# MAGIC | `noul` | `probability` (0–1) that a statement is true | flags, yes/no checks, gating |
# MAGIC | `choice` | `choice` label + per-label `probabilities` + `confidence` | classification, tagging, routing |
# MAGIC | `score` | `score` on an ordered scale + `legend` + `confidence` | severity, quality, complexity |
# MAGIC
# MAGIC ```sql
# MAGIC ai_decide(state, questions [, options])  -- returns VARIANT
# MAGIC ```
# MAGIC
# MAGIC This notebook covers the use cases from the [launch blog](https://www.databricks.com/blog/introducing-aidecide-make-fast-decisions-your-governed-data):
# MAGIC
# MAGIC 1. **Hello world**: all three question types in one call
# MAGIC 2. **Review analysis**: tag product reviews at scale with SQL
# MAGIC 3. **Model routing**: score prompt complexity and send each prompt to a small or large model
# MAGIC 4. **AI judge**: check generated answers against a policy
# MAGIC 5. **Real-time decisions**: call the REST API from Python and measure latency
# MAGIC
# MAGIC **Requirements**
# MAGIC * Serverless or DBR **15.4 LTS+** (18.2+ recommended), or a Pro/Serverless SQL warehouse. Databricks SQL Classic is **not** supported.
# MAGIC * `ai_decide` preview turned on by a workspace admin (**Previews** page), in a [supported region](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_decide).
# MAGIC
# MAGIC Docs: [SQL reference](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_decide) · [REST API](https://docs.databricks.com/api/ai-functions/v1/ai-decide)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Setup
# MAGIC Choose a catalog and schema you can write to. The demo creates three small tables in it.

# COMMAND ----------

dbutils.widgets.text("catalog", "main", "Catalog")
dbutils.widgets.text("schema", "ai_decide_demo", "Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")
spark.sql(f"USE `{catalog}`.`{schema}`")
print(f"Using {catalog}.{schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Hello world: three question types in one call
# MAGIC `state` can be plain text or JSON. `questions` is a **constant** JSON object that maps question IDs to their definitions.
# MAGIC A `noul` question doesn't need `criteria`. A `choice` takes 1–255 labels. A `score` takes 2–10 ordered levels, lowest first.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT ai_decide(
# MAGIC   '{"name": "TrailShell jacket", "description": "Lightweight waterproof hiking jacket made from recycled polyester. Packs into its own pocket."}',
# MAGIC   '{
# MAGIC     "category": {
# MAGIC       "type": "choice",
# MAGIC       "instructions": "Which product category best fits this item?",
# MAGIC       "criteria": {
# MAGIC         "outerwear": "Jackets, coats, and other protective outer layers",
# MAGIC         "footwear": "Shoes, boots, and sandals",
# MAGIC         "accessories": "Bags, hats, and other accessories"
# MAGIC       }
# MAGIC     },
# MAGIC     "recycled_materials": {
# MAGIC       "type": "noul",
# MAGIC       "instructions": "Does the listing state that the product uses recycled materials?"
# MAGIC     },
# MAGIC     "hiking_suitability": {
# MAGIC       "type": "score",
# MAGIC       "instructions": "How suitable is this product for hiking in rainy weather?",
# MAGIC       "criteria": [
# MAGIC         "Not suitable for outdoor use in rain",
# MAGIC         "Offers some protection from rain",
# MAGIC         "Designed for hiking with waterproof protection"
# MAGIC       ]
# MAGIC     }
# MAGIC   }',
# MAGIC   map('version', '1.0')
# MAGIC ) AS decision

# COMMAND ----------

# MAGIC %md
# MAGIC The result is a `VARIANT`. Use path syntax with a cast to pull out typed columns:

# COMMAND ----------

# MAGIC %sql
# MAGIC WITH d AS (
# MAGIC   SELECT ai_decide(
# MAGIC     'Lightweight waterproof hiking jacket made from recycled polyester. Packs into its own pocket.',
# MAGIC     '{
# MAGIC       "category": {"type": "choice", "instructions": "Which product category best fits this item?",
# MAGIC                    "criteria": {"outerwear": "Jackets and coats", "footwear": "Shoes and boots", "accessories": "Bags and hats"}},
# MAGIC       "recycled_materials": {"type": "noul", "instructions": "Does the listing state that the product uses recycled materials?"},
# MAGIC       "hiking_suitability": {"type": "score", "instructions": "How suitable is this product for hiking in rainy weather?",
# MAGIC                              "criteria": ["Not suitable for rain", "Some rain protection", "Designed for wet-weather hiking"]}
# MAGIC     }'
# MAGIC   ) AS decision
# MAGIC )
# MAGIC SELECT
# MAGIC   decision:response.answers.category.choice::string                AS category,
# MAGIC   decision:response.answers.category.confidence::double            AS category_confidence,
# MAGIC   decision:response.answers.category.probabilities                 AS category_probabilities,
# MAGIC   decision:response.answers.recycled_materials.probability::double AS p_recycled,
# MAGIC   decision:response.answers.hiking_suitability.score::double       AS hiking_score,   -- 0 = lowest level, 2 = highest
# MAGIC   decision:response.answers.hiking_suitability.legend              AS hiking_legend,
# MAGIC   decision:error_message::string                                   AS error_message
# MAGIC FROM d

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Review analysis at scale
# MAGIC Load some sample product reviews, then tag each one in a single SQL pass with:
# MAGIC * the **primary issue** (`choice`)
# MAGIC * the **likelihood of a return** (`noul`)
# MAGIC * **sentiment severity** (`score`)

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE product_reviews AS
# MAGIC SELECT * FROM VALUES
# MAGIC   (1,  'TrailShell Jacket', 'Soaked through after 20 minutes of light drizzle. "Waterproof" my foot. Sending it back.'),
# MAGIC   (2,  'TrailShell Jacket', 'Love it! Packs tiny, kept me dry on a 3 day trek in Scotland.'),
# MAGIC   (3,  'Summit Boots',      'Ordered a 10, feels like an 8.5. Toes are crushed. Need a bigger size.'),
# MAGIC   (4,  'Summit Boots',      'Took 6 weeks to arrive and the box was crushed. Boots themselves are fine.'),
# MAGIC   (5,  'Summit Boots',      'Sole started peeling off after two hikes. Really poor glue job.'),
# MAGIC   (6,  'Ridge Daypack',     'Great pack but $180 is steep for what it is. Similar packs are half the price.'),
# MAGIC   (7,  'Ridge Daypack',     'Zipper broke on day one. Customer support never answered my emails.'),
# MAGIC   (8,  'Ridge Daypack',     'Perfect size for day hikes, lots of pockets, comfortable straps.'),
# MAGIC   (9,  'Alpine Beanie',     'Color looks nothing like the photos, it is bright orange not rust. Returning.'),
# MAGIC   (10, 'Alpine Beanie',     'Warm and soft. Bought a second one for my partner.'),
# MAGIC   (11, 'TrailShell Jacket', 'Fits ok, a bit boxy. Does the job I guess.'),
# MAGIC   (12, 'Summit Boots',      'Arrived with the wrong boots inside, completely different model.')
# MAGIC AS t(review_id, product, review_text);
# MAGIC
# MAGIC SELECT * FROM product_reviews;

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE product_reviews_tagged AS
# MAGIC WITH decided AS (
# MAGIC   SELECT
# MAGIC     *,
# MAGIC     ai_decide(
# MAGIC       -- state can be JSON built from columns, so the model sees structured context
# MAGIC       to_json(named_struct('product', product, 'review', review_text)),
# MAGIC       '{
# MAGIC         "primary_issue": {
# MAGIC           "type": "choice",
# MAGIC           "instructions": "What is the primary issue raised in this product review?",
# MAGIC           "criteria": {
# MAGIC             "quality":   "Product is defective, broke, or did not perform as advertised",
# MAGIC             "sizing":    "Product fit or size is wrong",
# MAGIC             "shipping":  "Late delivery, damaged packaging, or wrong item sent",
# MAGIC             "price":     "Product is considered too expensive or poor value",
# MAGIC             "appearance":"Product looks different from the listing or photos",
# MAGIC             "service":   "Customer support was unhelpful or unresponsive",
# MAGIC             "none":      "The review is positive or raises no real issue"
# MAGIC           }
# MAGIC         },
# MAGIC         "will_return": {
# MAGIC           "type": "noul",
# MAGIC           "instructions": "Is the customer likely to return or exchange the product?",
# MAGIC           "criteria": {
# MAGIC             "true":  "The customer says or strongly implies they will return, exchange, or send the product back",
# MAGIC             "false": "The customer intends to keep the product"
# MAGIC           }
# MAGIC         },
# MAGIC         "severity": {
# MAGIC           "type": "score",
# MAGIC           "instructions": "How negative is this review?",
# MAGIC           "criteria": [
# MAGIC             "Positive, the customer is happy",
# MAGIC             "Neutral or mildly mixed",
# MAGIC             "Negative, the customer is disappointed",
# MAGIC             "Very negative, the customer is angry or feels misled"
# MAGIC           ]
# MAGIC         }
# MAGIC       }'
# MAGIC     ) AS decision
# MAGIC   FROM product_reviews
# MAGIC )
# MAGIC SELECT
# MAGIC   review_id, product, review_text,
# MAGIC   decision:response.answers.primary_issue.choice::string        AS primary_issue,
# MAGIC   decision:response.answers.primary_issue.confidence::double    AS issue_confidence,
# MAGIC   decision:response.answers.will_return.probability::double     AS p_return,
# MAGIC   decision:response.answers.severity.score::double              AS severity_score,  -- 0..3
# MAGIC   decision:error_message::string                                AS error_message,
# MAGIC   decision
# MAGIC FROM decided;
# MAGIC
# MAGIC SELECT review_id, product, review_text, primary_issue,
# MAGIC        round(issue_confidence, 2) AS issue_confidence,
# MAGIC        round(p_return, 2)         AS p_return,
# MAGIC        round(severity_score, 2)   AS severity_score
# MAGIC FROM product_reviews_tagged
# MAGIC ORDER BY review_id;

# COMMAND ----------

# MAGIC %md
# MAGIC Once the decisions are columns, they're ordinary governed data you can aggregate, put on a dashboard, or route to downstream processes.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Issue breakdown per product, with expected returns
# MAGIC SELECT
# MAGIC   product,
# MAGIC   primary_issue,
# MAGIC   count(*)                       AS reviews,
# MAGIC   round(sum(p_return), 2)        AS expected_returns,
# MAGIC   round(avg(severity_score), 2)  AS avg_severity
# MAGIC FROM product_reviews_tagged
# MAGIC GROUP BY ALL
# MAGIC ORDER BY product, reviews DESC;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Action queue: high-confidence return risks for the retention team
# MAGIC SELECT review_id, product, review_text, primary_issue, round(p_return, 2) AS p_return
# MAGIC FROM product_reviews_tagged
# MAGIC WHERE p_return >= 0.7
# MAGIC ORDER BY p_return DESC;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Model routing by prompt complexity
# MAGIC Sending every prompt to a frontier LLM costs more than it needs to. `ai_decide` can score complexity in a fraction of a second,
# MAGIC so simple prompts go to a small model and only hard ones go to a large model.
# MAGIC
# MAGIC > Replace the endpoint names in the `CASE` with serving endpoints from your workspace (**Serving** page).

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE user_prompts AS
# MAGIC SELECT * FROM VALUES
# MAGIC   (1, 'What is the capital of France?'),
# MAGIC   (2, 'Translate "good morning" into Spanish.'),
# MAGIC   (3, 'Write a SQL query that returns the top 3 products by revenue per region, handling ties, from tables orders(order_id, product_id, region, amount) and products(product_id, name).'),
# MAGIC   (4, 'Summarize this sentence in five words: The quarterly meeting was moved to Thursday afternoon.'),
# MAGIC   (5, 'Design a multi-region, active-active architecture for a payments ledger that guarantees exactly-once processing, and explain the consistency trade-offs.'),
# MAGIC   (6, 'Prove that there are infinitely many primes and then generalize the argument to primes of the form 4k+3.'),
# MAGIC   (7, 'Is a tomato a fruit or a vegetable?')
# MAGIC AS t(prompt_id, prompt);
# MAGIC
# MAGIC CREATE OR REPLACE TABLE routed_prompts AS
# MAGIC WITH d AS (
# MAGIC   SELECT *,
# MAGIC     ai_decide(prompt, '{
# MAGIC       "complexity": {
# MAGIC         "type": "score",
# MAGIC         "instructions": "How much reasoning is required to answer this prompt well?",
# MAGIC         "criteria": [
# MAGIC           "Trivial lookup, translation, or short factual answer",
# MAGIC           "Simple task needing a few steps",
# MAGIC           "Moderate task needing structured reasoning or code",
# MAGIC           "Hard task needing deep multi-step reasoning, proofs, or system design"
# MAGIC         ]
# MAGIC       },
# MAGIC       "needs_code": {
# MAGIC         "type": "noul",
# MAGIC         "instructions": "Does answering this prompt require writing code or a query?"
# MAGIC       }
# MAGIC     }') AS decision
# MAGIC   FROM user_prompts
# MAGIC )
# MAGIC SELECT
# MAGIC   prompt_id, prompt,
# MAGIC   decision:response.answers.complexity.score::double        AS complexity,   -- 0..3
# MAGIC   decision:response.answers.needs_code.probability::double  AS p_code,
# MAGIC   CASE
# MAGIC     WHEN decision:response.answers.complexity.score::double >= 1.5 THEN 'databricks-claude-opus-5-5'   -- large model
# MAGIC     ELSE 'databricks-claude-haiku-4-5'                                                                -- small model
# MAGIC   END AS routed_endpoint
# MAGIC FROM d;
# MAGIC
# MAGIC SELECT prompt_id, prompt, round(complexity, 2) AS complexity, round(p_code, 2) AS p_code, routed_endpoint
# MAGIC FROM routed_prompts ORDER BY prompt_id;

# COMMAND ----------

# MAGIC %md
# MAGIC **Optional:** run each prompt on its routed model with `ai_query`. Because `ai_query` needs a constant endpoint name, run one call per route and `UNION ALL` the results.
# MAGIC Uncomment the cell to try it. It calls real LLM endpoints and you'll be billed for them.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- SELECT prompt_id, routed_endpoint, ai_query('databricks-claude-haiku-4-5', prompt) AS answer
# MAGIC -- FROM routed_prompts WHERE routed_endpoint = 'databricks-claude-haiku-4-5'
# MAGIC -- UNION ALL
# MAGIC -- SELECT prompt_id, routed_endpoint, ai_query('databricks-claude-opus-5-5', prompt) AS answer
# MAGIC -- FROM routed_prompts WHERE routed_endpoint = 'databricks-claude-opus-5-5'
# MAGIC -- ORDER BY prompt_id;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. `ai_decide` as an AI judge
# MAGIC Check support-bot answers against a refund policy. The `state` is a JSON object that holds the policy, the customer question, and the bot's answer,
# MAGIC so the decision model can evaluate the answer in context. This works as a fast guardrail before a response reaches the customer, or as an offline eval.

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE bot_answers AS
# MAGIC SELECT * FROM VALUES
# MAGIC   (1, 'Can I return my boots after 45 days?',
# MAGIC       'Unfortunately our return window is 30 days, so we cannot accept a return at 45 days. Your boots are covered by our 1-year warranty against defects, though.'),
# MAGIC   (2, 'Can I return my boots after 45 days?',
# MAGIC       'Sure! Just send them back and we will refund you in full, no questions asked.'),
# MAGIC   (3, 'My jacket arrived damaged, what do I do?',
# MAGIC       'Sorry about that! Reply with a photo and we will ship a free replacement right away. You do not need to return the damaged one.'),
# MAGIC   (4, 'Do you price match?',
# MAGIC       'Ugh, read the FAQ. We do not do that.'),
# MAGIC   (5, 'How long do refunds take?',
# MAGIC       'Refunds are issued to the original payment method within 5-7 business days after we receive the item.')
# MAGIC AS t(answer_id, customer_question, bot_answer);
# MAGIC
# MAGIC WITH judged AS (
# MAGIC   SELECT *,
# MAGIC     ai_decide(
# MAGIC       to_json(named_struct(
# MAGIC         'policy', 'Returns accepted within 30 days of delivery for a full refund. Items damaged in shipping are replaced free of charge; no return of the damaged item is required. Refunds are issued within 5-7 business days of receipt. We do not price match. Agents must be polite and professional.',
# MAGIC         'customer_question', customer_question,
# MAGIC         'bot_answer', bot_answer
# MAGIC       )),
# MAGIC       '{
# MAGIC         "policy_compliant": {
# MAGIC           "type": "noul",
# MAGIC           "instructions": "Is the bot_answer consistent with the policy?",
# MAGIC           "criteria": {
# MAGIC             "true":  "Every claim and promise in the answer is allowed by the policy",
# MAGIC             "false": "The answer promises something the policy does not allow or misstates the policy"
# MAGIC           }
# MAGIC         },
# MAGIC         "tone": {
# MAGIC           "type": "choice",
# MAGIC           "instructions": "What is the tone of the bot_answer toward the customer?",
# MAGIC           "criteria": {
# MAGIC             "professional": "Polite, empathetic, and professional",
# MAGIC             "neutral":      "Matter-of-fact without warmth or rudeness",
# MAGIC             "rude":         "Dismissive, condescending, or rude"
# MAGIC           }
# MAGIC         },
# MAGIC         "helpfulness": {
# MAGIC           "type": "score",
# MAGIC           "instructions": "How fully does the bot_answer resolve the customer_question?",
# MAGIC           "criteria": ["Does not address the question", "Partially addresses it", "Fully resolves it with clear next steps"]
# MAGIC         }
# MAGIC       }'
# MAGIC     ) AS decision
# MAGIC   FROM bot_answers
# MAGIC )
# MAGIC SELECT
# MAGIC   answer_id, customer_question, bot_answer,
# MAGIC   round(decision:response.answers.policy_compliant.probability::double, 2) AS p_compliant,
# MAGIC   decision:response.answers.tone.choice::string                           AS tone,
# MAGIC   round(decision:response.answers.helpfulness.score::double, 2)           AS helpfulness,  -- 0..2
# MAGIC   CASE
# MAGIC     WHEN decision:response.answers.policy_compliant.probability::double < 0.5 THEN 'BLOCK: policy violation'
# MAGIC     WHEN decision:response.answers.tone.choice::string = 'rude'              THEN 'BLOCK: tone'
# MAGIC     ELSE 'PASS'
# MAGIC   END AS verdict
# MAGIC FROM judged
# MAGIC ORDER BY answer_id;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Real-time decisions with the REST API
# MAGIC Apps and agents can call `POST /api/2.0/ai-functions/ai-decide` directly. In this case `state` and `questions` are JSON objects, not strings.
# MAGIC The cell below uses the Databricks SDK, which reads auth from the notebook context. Outside a notebook it reads your usual profile or env vars.
# MAGIC
# MAGIC The example below is a live support-chat triage: decide the queue and urgency for each incoming message before a human or agent sees it.

# COMMAND ----------

# MAGIC %pip install -q --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

import time
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

TRIAGE_QUESTIONS = {
    "queue": {
        "type": "choice",
        "instructions": "Which support queue should handle this message?",
        "criteria": {
            "billing": "Charges, refunds, invoices, payment methods",
            "orders": "Order status, shipping, delivery, wrong items",
            "product": "How to use a product, sizing, defects",
            "account": "Login, password, profile, account deletion",
        },
    },
    "urgent": {
        "type": "noul",
        "instructions": "Does this message need an immediate human response?",
        "criteria": {
            "true": "Customer is very upset, mentions fraud, safety, legal action, or a time-critical problem",
            "false": "Routine request that can wait in the normal queue",
        },
    },
}


def ai_decide(state, questions, version="1.0"):
    """Call the ai_decide REST API and return the response answers map."""
    resp = w.api_client.do(
        "POST",
        "/api/2.0/ai-functions/ai-decide",
        body={"state": state, "questions": questions, "options": {"version": version}},
    )
    return resp["response"]["answers"]


messages = [
    "I was charged twice for order #4411, please refund the duplicate.",
    "Where is my package? Tracking hasn't updated in a week.",
    "Someone logged into my account from another country and placed orders! Help NOW.",
    "What size Summit Boots should I get if I'm usually a 10.5?",
    "How do I change the email address on my profile?",
]

for msg in messages:
    t0 = time.perf_counter()
    a = ai_decide({"message": msg}, TRIAGE_QUESTIONS)
    ms = (time.perf_counter() - t0) * 1000
    print(
        f"{ms:6.0f} ms | queue={a['queue']['choice']:<8} "
        f"(conf {a['queue']['confidence']:.2f}) | p_urgent={a['urgent']['probability']:.2f} | {msg}"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ### Latency check
# MAGIC Fire a batch of single-question requests to get a rough look at round-trip latency from the notebook, including network and auth overhead.

# COMMAND ----------

import statistics

latencies = []
q = {"urgent": TRIAGE_QUESTIONS["urgent"]}
for i in range(20):
    t0 = time.perf_counter()
    ai_decide({"message": messages[i % len(messages)]}, q)
    latencies.append((time.perf_counter() - t0) * 1000)

latencies.sort()
print(f"n={len(latencies)}  p50={statistics.median(latencies):.0f} ms  "
      f"p90={latencies[int(0.9 * len(latencies)) - 1]:.0f} ms  max={latencies[-1]:.0f} ms")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Tips and limitations
# MAGIC * **Questions must be constant.** Only `state` can vary per row. To ask different questions, use separate calls or a `CASE`.
# MAGIC * **Batch questions.** One call can answer several questions about the same `state`, which costs less than several calls.
# MAGIC * **Write good `criteria`.** Short, mutually exclusive descriptions work best. Add a catch-all label such as `none` to a `choice`.
# MAGIC * **Score order matters.** List `score` criteria from lowest to highest. `score` is a probability-weighted index (0 to n-1), and `legend` maps each index to its description.
# MAGIC * **Limits:** a `choice` takes up to 255 labels and a `score` takes 2–10 levels.
# MAGIC * **Check `error_message`** in the result and filter or retry rows where it isn't null.
# MAGIC * **Pin `map('version', '1.0')`** in production so results stay consistent as new model versions ship.
# MAGIC * **`ai_decide` vs an LLM.** Use `ai_decide` for classification, gating, scoring, and routing, where you need speed and calibrated probabilities. Use `ai_query` when you need generated text.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cleanup

# COMMAND ----------

# dbutils.widgets.get works again after the Python restart in section 5
# spark.sql(f"DROP SCHEMA IF EXISTS `{dbutils.widgets.get('catalog')}`.`{dbutils.widgets.get('schema')}` CASCADE")
