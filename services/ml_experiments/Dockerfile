FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ml_experiments ./ml_experiments
USER 65532:65532
EXPOSE 8002
CMD ["opentelemetry-instrument", "uvicorn", "ml_experiments.main:app", "--host", "0.0.0.0", "--port", "8002"]
