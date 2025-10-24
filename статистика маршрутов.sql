-- Статистика по расписанию
SELECT 
  category as "Категория",
  COUNT(*) as "Всего рейсов",
  COUNT(DISTINCT route_id) as "Уникальных маршрутов",
  MIN(start_datetime) as "Первая дата",
  MAX(start_datetime) as "Последняя дата",
  ROUND(AVG(total_time_minutes), 1) as "Среднее время (мин)",
  ROUND(AVG(total_price), 2) as "Средняя стоимость"
FROM route_schedule
GROUP BY category
ORDER BY category;

-- Проверка распределения по дням
SELECT 
  category,
  TRUNC(start_datetime) as date_day,
  COUNT(*) as trips_count,
  TO_CHAR(MIN(start_datetime), 'HH24:MI') as first_trip,
  TO_CHAR(MAX(start_datetime), 'HH24:MI') as last_trip
FROM route_schedule
WHERE TRUNC(start_datetime) BETWEEN TRUNC(SYSDATE) AND TRUNC(SYSDATE) + 7
GROUP BY category, TRUNC(start_datetime)
ORDER BY date_day, category;

-- Пример выборки расписания на ближайшие дни
SELECT 
  r.route_name as "Маршрут",
  rs.category as "Категория",
  rs.cities_sequence as "Путь",
  TO_CHAR(rs.start_datetime, 'DD.MM.YYYY HH24:MI') as "Отправление",
  TO_CHAR(rs.end_datetime, 'DD.MM.YYYY HH24:MI') as "Прибытие",
  rs.total_time_minutes as "Время (мин)",
  rs.total_price as "Стоимость"
FROM route_schedule rs
JOIN route r ON rs.route_id = r.id
WHERE rs.start_datetime BETWEEN SYSDATE AND SYSDATE + 3
ORDER BY rs.start_datetime, r.route_name
FETCH FIRST 20 ROWS ONLY;