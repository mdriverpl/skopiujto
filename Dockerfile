FROM node:22-alpine AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.12-slim AS application
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-dejavu-extra && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && useradd --uid 10001 --create-home app \
    && mkdir -p /app/data && chown app:app /app/data
COPY backend ./backend
# Check PDF dependencies in the actual Linux image before publishing it.
RUN python -c "from backend.document_pdf import render_pdf; assert render_pdf({'title': 'PDF build check', 'content': 'PDF check'}).startswith(b'%PDF-')"
COPY --from=frontend /build/dist ./dist
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
