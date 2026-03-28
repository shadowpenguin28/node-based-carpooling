#!/bin/sh

echo "Waiting for PostgreSQL..."
while ! nc -z $DB_HOST $DB_PORT; do
    sleep 0.1
done
echo "PostgreSQL started"

python manage.py migrate

gunicorn carpool.wsgi:application --bind 0.0.0.0:8000