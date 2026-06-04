FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=fr_FR.UTF-8 \
    LC_TIME=fr_FR.UTF-8 \
    MUSL_LOCPATH=/usr/share/i18n/locales/musl

WORKDIR /app

RUN apk add --no-cache musl-locales musl-locales-lang

COPY . .

EXPOSE 8000
VOLUME ["/app/data"]

CMD ["python", "-c", "import app; app.run(host='0.0.0.0', port=8000)"]
