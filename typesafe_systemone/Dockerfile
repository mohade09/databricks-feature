FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
# Host HTTP_PROXY (e.g. 127.0.0.1 from Cursor) is not reachable inside the container.
ENV PIP_INDEX_URL=https://pypi-proxy.cloud.databricks.com/simple
RUN HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy= ALL_PROXY= all_proxy= \
    pip install --no-cache-dir --proxy="" -r requirements.txt

COPY query_systemone.py .

ENTRYPOINT ["python", "query_systemone.py"]
