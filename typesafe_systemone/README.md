# TypeSafe System One

Query a Unity Catalog model service through the System One AI Gateway route.

Put `DATABRICKS_HOST` and `DATABRICKS_TOKEN` in `../.env`, then from this folder:

```bash
podman build -t systemone-query .
podman run --rm --env-file ../.env systemone-query --message "Where is my package?"
```
