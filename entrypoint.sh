#!/bin/sh

echo "Waiting for PostgreSQL..."
python << END
import socket
import time
import os

host = os.environ.get('DB_HOST', 'db')
port = int(os.environ.get('DB_PORT', 5432))

while True:
    try:
        sock = socket.create_connection((host, port), timeout=1)
        sock.close()
        break
    except (socket.error, ConnectionRefusedError):
        time.sleep(0.1)
END

echo "PostgreSQL started"
python manage.py migrate
python manage.py runserver 0.0.0.0:8000