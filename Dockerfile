FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --retries 5 --timeout 60 -r requirements.txt

COPY . /app
ENV PYTHONPATH=/app

# The container exposes the optional REST interface (server/main.py).
# The MCP stdio server is normally run on the host, e.g.:
#   docker run --rm -it -e CTFD_BASE_URL=$CTFD_BASE_URL ctfd-mcp python ctfd_mcp_server.py
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]