FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY recognition ./recognition
USER 65532:65532
EXPOSE 8003
CMD ["opentelemetry-instrument", "uvicorn", "recognition.main:app", "--host", "0.0.0.0", "--port", "8003"]
