# Stage 1: Build do frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Runtime Python com frontend embutido
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

WORKDIR /app/backend

EXPOSE 8080

# Railway injeta a variável PORT dinamicamente
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
