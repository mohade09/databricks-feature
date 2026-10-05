# Databricks Features

This repo collects hands-on demos of Databricks features. Each feature has its own folder with a notebook you can import into a Databricks workspace and run from start to finish.

## Features

| Feature | Folder | Description |
|---|---|---|
| `ai_decide` | [`ai_decide/`](ai_decide/) | Fast, structured decisions on governed data with the `ai_decide` AI Function: review tagging, routing prompts to models by complexity, AI-as-judge policy checks, and real-time calls through the REST API. |

## Using a demo

1. In your Databricks workspace, go to **Workspace → Import** and select the notebook file from the feature's folder. You can also import it from the CLI:
   ```bash
   databricks workspace import /Users/<you>/<notebook> --file <folder>/<notebook>.py --format SOURCE --language PYTHON
   ```
2. Attach the notebook to serverless compute or a supported cluster.
3. Set the catalog and schema widgets at the top of the notebook, then run all cells.

Each notebook lists its own requirements, such as runtime version and any previews that must be turned on.

## Adding a feature

Create a folder named after the feature and put a notebook inside it in Databricks source format (`.py`). Then add a row to the table above.
