FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN python -m pip install --no-cache-dir torch==2.14.0+cpu --index-url https://download.pytorch.org/whl/cpu
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml README.md ./
COPY src src
RUN python -m pip install --no-cache-dir --no-deps .

CMD ["python", "-m", "jevops.streaming.decision_service"]
