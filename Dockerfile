# Сборка сайта
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Сервер
FROM python:3.13-slim
# Tesseract читает фото чеков, присланные в Telegram-бота (в приложении и на сайте чек
# читается прямо на устройстве).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=web /web/dist ./frontend/dist
ENV DATA_DIR=/data \
    FRONTEND_DIST=/app/frontend/dist
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
