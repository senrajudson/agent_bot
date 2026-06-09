FROM python:3.12-slim

WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy Poetry files
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only=main

# Copy app code
COPY app ./app

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]