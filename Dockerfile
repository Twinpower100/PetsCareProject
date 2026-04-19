FROM python:3.11-slim

# Установка системных зависимостей для PostGIS / GDAL
RUN apt-get update && apt-get install -y \
    binutils \
    libproj-dev \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/PetsCare
ENV DJANGO_SETTINGS_MODULE=settings

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

COPY . .

# Создаём директорию для логов (она исключена из .dockerignore)
RUN mkdir -p /app/logs && chown -R app:app /app

# Копируем патч миграций в установленные пакеты (для пакетов, у которых в PyPI
# нет миграций, сгенерированных Django 5.x для BigAutoField).
RUN cp -r /app/deploy/migrations_patch/push_notifications/*.py \
    /usr/local/lib/python3.11/site-packages/push_notifications/migrations/

WORKDIR /app/PetsCare

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "wsgi:application"]
