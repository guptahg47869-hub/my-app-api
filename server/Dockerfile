FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (optional, but good for debugging)
RUN apt-get update && apt-get install -y --no-install-recommends     curl build-essential && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
RUN pip install --upgrade pip &&     pip install -e .

COPY app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
