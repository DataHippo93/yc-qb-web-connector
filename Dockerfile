FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for lxml / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" || \
    pip install --no-cache-dir \
        fastapi \
        uvicorn[standard] \
        spyne \
        lxml \
        supabase \
        pydantic-settings \
        structlog \
        tenacity \
        pyyaml \
        psycopg2-binary \
        python-dotenv

# Copy source
COPY . .

# Runtime
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
