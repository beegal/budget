FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY app.py database.py web_helpers.py initial-data.yaml endpoints static ./

EXPOSE 8000
VOLUME ["/app/data"]

CMD ["python", "-c", "import app; app.run(host='0.0.0.0', port=8000)"]
