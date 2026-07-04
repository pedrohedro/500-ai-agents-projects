# Monetization Platform — production image.
# Build context MUST be the repository root so the sibling agent packages are
# copied in and importable by the adapters:
#   docker build -f monetization_platform/Dockerfile -t agent-api-cloud .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install platform dependencies first (better layer caching).
COPY monetization_platform/requirements.txt /app/monetization_platform/requirements.txt
RUN pip install --no-cache-dir -r /app/monetization_platform/requirements.txt

# Copy the platform plus the four agent packages it wraps.
COPY monetization_platform /app/monetization_platform
COPY marketing_content_agent /app/marketing_content_agent
COPY legal_doc_reviewer_agent /app/legal_doc_reviewer_agent
COPY support_chatbot_agent /app/support_chatbot_agent
COPY hr_resume_screening_agent /app/hr_resume_screening_agent

# Install optional agent dependencies (best-effort; agents fall back to mock).
RUN pip install --no-cache-dir -r /app/marketing_content_agent/requirements.txt || true \
 && pip install --no-cache-dir -r /app/legal_doc_reviewer_agent/requirements.txt || true \
 && pip install --no-cache-dir -r /app/support_chatbot_agent/requirements.txt || true \
 && pip install --no-cache-dir -r /app/hr_resume_screening_agent/requirements.txt || true

EXPOSE 8000

# Render/Railway inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn monetization_platform.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
