FROM python:3.12-slim
WORKDIR /app
COPY services/migrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/migrator/migrate.py .
COPY services/data_protocol/migrations /migrations/data_protocol
COPY services/ml_experiments/migrations /migrations/ml_experiments
COPY services/recognition/migrations /migrations/recognition
COPY database/service_roles.sql /migrations/service_roles.sql
CMD ["python", "migrate.py"]
