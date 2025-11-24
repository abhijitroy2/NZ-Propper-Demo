FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Expose port (Railway will set PORT env var)
EXPOSE 8000

# Run the application (use PORT env var from Railway)
# Railway sets PORT automatically, default to 8000 if not set
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"


