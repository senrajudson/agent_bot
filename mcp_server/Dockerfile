FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry==2.3.2

# Copy domain package first (dependency)
COPY domain/ /app/domain/
COPY mcp_server/pyproject.toml /app/pyproject.toml
COPY mcp_server/poetry.lock /app/poetry.lock

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only=main --no-root

COPY mcp_server/ /app/mcp_server/

EXPOSE 8005

CMD ["python", "-m", "mcp_server.server"]
