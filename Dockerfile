FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Default command (overridden per service in docker-compose)
CMD ["python", "-m", "backend.quantix_core.api.main"]
