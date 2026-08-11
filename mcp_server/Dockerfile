FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY data ./data

EXPOSE 8000

CMD ["sh", "-c", "uvicorn review_mcp.app:app --host ${MCP_HOST:-0.0.0.0} --port ${MCP_PORT:-8000}"]
