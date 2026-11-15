FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY data_protocol ./data_protocol
USER 65532:65532
EXPOSE 8001
CMD ["opentelemetry-instrument", "uvicorn", "data_protocol.main:app", "--host", "0.0.0.0", "--port", "8001"]
