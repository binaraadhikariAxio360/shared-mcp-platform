FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "import langgraph, langchain_core, langchain_google_genai"

COPY . .

EXPOSE 8000

# No --reload: startup runs init_db_and_seed(), so code edits must not restart the app implicitly.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
