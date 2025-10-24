#!/bin/bash
# start_services.sh

echo "🚀 Starting both services..."

# Запускаем основное приложение на порту 8000
echo "Starting main app on port 8000..."
gunicorn -w 2 -b 0.0.0.0:8000 --timeout 60 --log-level info app_register_nodb:app &

# Ждем немного перед запуском второго приложения
sleep 5

# Запускаем приложение поиска маршрутов на порту 5001
echo "Starting routes app on port 5001..."
gunicorn -w 2 -b 0.0.0.0:5001 --timeout 60 --log-level info app_routes:app &

# Ждем завершения всех процессов
echo "All services started. Monitoring..."
wait