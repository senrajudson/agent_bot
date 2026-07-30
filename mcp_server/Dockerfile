FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry

# Copy domain package first (dependency)
COPY domain/ /app/domain/
COPY mcp_server/pyproject.toml /app/pyproject.toml

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only=main --no-root

COPY mcp_server/ /app/mcp_server/

EXPOSE 8005

CMD ["python", "-m", "mcp_server.server"]
