# Build context is market_system/ (this file's directory) — needed so the
# image can include both backend/ and frontend/. On Railway/Render/Fly, set
# the service's root/source directory to market_system/ and they'll find
# this Dockerfile automatically.
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY frontend ./frontend

ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
