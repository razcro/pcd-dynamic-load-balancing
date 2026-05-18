FROM grafana/k6:0.55.0 AS k6-stage

FROM python:3.12-slim
COPY --from=k6-stage /usr/bin/k6 /usr/bin/k6

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

CMD ["python", "app.py"]
