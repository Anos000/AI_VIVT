-- 1. Создаем представление для двунаправленных путей
CREATE OR REPLACE VIEW v_city_path_dir AS
SELECT city_a_id AS from_city_id, city_b_id AS to_city_id, dist_km FROM city_path
UNION ALL
SELECT city_b_id AS from_city_id, city_a_id AS to_city_id, dist_km FROM city_path;



-- УНИВЕРСАЛЬНЫЙ поиск всех возможных путей для ВСЕХ маршрутов
WITH route_paths (route_id, current_city_id, path, distance, depth, visited, city_names, city_ids, end_city_id) AS (
  -- Базовый случай: начинаем из начального города каждого маршрута
  SELECT 
    r.id,
    r.start_city_id, 
    CAST(r.start_city_id AS VARCHAR2(1000)), 
    0, 
    0,
    CAST(r.start_city_id AS VARCHAR2(1000)),
    (SELECT name FROM city WHERE id = r.start_city_id),
    CAST(r.start_city_id AS VARCHAR2(1000)),
    r.end_city_id
  FROM route r
  
  UNION ALL
  
  -- Рекурсивный случай: расширяем пути
  SELECT 
    p.route_id,
    cp.to_city_id,
    p.path || '->' || cp.to_city_id,
    p.distance + cp.dist_km,
    p.depth + 1,
    p.visited || ',' || cp.to_city_id,
    p.city_names || ' → ' || (SELECT name FROM city WHERE id = cp.to_city_id),
    p.city_ids || ',' || cp.to_city_id,
    p.end_city_id
  FROM route_paths p
  JOIN v_city_path_dir cp ON p.current_city_id = cp.from_city_id
  WHERE p.depth < 8  -- Ограничение глубины
    AND INSTR(',' || p.visited || ',', ',' || cp.to_city_id || ',') = 0
    AND p.current_city_id != p.end_city_id  -- Останавливаемся при достижении цели
)
SELECT 
  r.route_name as "Маршрут",
  start_city.name as "Город отправления",
  end_city.name as "Город назначения",
  rp.city_names as "Полный путь",
  rp.distance as "Общее расстояние (км)",
  rp.depth as "Количество пересадок",
  (rp.depth - 1) as "Промежуточных городов",
  -- Извлекаем промежуточные ID городов
  CASE 
    WHEN rp.depth > 1 THEN 
      SUBSTR(
        rp.city_ids,
        INSTR(rp.city_ids, ',', 1, 1) + 1,
        INSTR(rp.city_ids, ',', 1, rp.depth) - INSTR(rp.city_ids, ',', 1, 1) - 1
      )
    ELSE NULL
  END as "ID промежуточных городов",
  rp.path as "ID путь"
FROM route_paths rp
JOIN route r ON rp.route_id = r.id
JOIN city start_city ON r.start_city_id = start_city.id
JOIN city end_city ON r.end_city_id = end_city.id
WHERE rp.current_city_id = rp.end_city_id  -- Только завершенные маршруты
ORDER BY 
  r.id,  -- Сначала группируем по маршрутам
  rp.distance,  -- Сортируем по расстоянию
  rp.depth    -- Затем по количеству пересадок