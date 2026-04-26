FROM python:3.11.9-slim

WORKDIR /app

# Install system dependencies needed by pdfplumber / poppler
RUN apt-get update && apt-get install -y \
    gcc \
    poppler-utils \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# No --reload in production (wastes memory, only for development)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]