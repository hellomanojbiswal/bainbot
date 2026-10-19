FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY dist ./dist
RUN useradd --create-home appuser && mkdir /app/data && chown appuser /app/data
USER appuser
ENV BAINBOT_DB=/app/data/bainbot.db
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
