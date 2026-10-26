FROM python:3.13-slim
WORKDIR /app
COPY server.py monitor_pages.py alert_worker.py .
USER 65534:65534
CMD ["python", "-B", "server.py"]
