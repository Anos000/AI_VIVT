-- МАКСИМАЛЬНЫЙ поиск всех возможных маршрутов с ID промежуточных городов
WITH paths (current_city_id, path, distance, depth, visited, city_names, city_ids) AS (
  SELECT 
    1, 
    '1', 
    0, 
    0,
    '1',
    'Москва',
    '1'  -- Начинаем с ID Москвы
  FROM dual
  
  UNION ALL
  
  SELECT 
    cp.to_city_id,
    p.path || '->' || cp.to_city_id,
    p.distance + cp.dist_km,
    p.depth + 1,
    p.visited || ',' || cp.to_city_id,
    p.city_names || ' → ' || (SELECT name FROM city WHERE id = cp.to_city_id),
    p.city_ids || ',' || cp.to_city_id
  FROM paths p
  JOIN v_city_path_dir cp ON p.current_city_id = cp.from_city_id
  WHERE p.depth < 10
    AND INSTR(',' || p.visited || ',', ',' || cp.to_city_id || ',') = 0
)
SELECT 
  city_names as "Полный маршрут",
  distance as "Общее расстояние",
  depth as "Пересадок",
  (depth - 1) as "Промежуточных городов",
  -- Извлекаем промежуточные города (исключаем первый и последний)
  CASE 
    WHEN depth > 1 THEN 
      SUBSTR(
        city_ids,
        INSTR(city_ids, ',', 1, 1) + 1,  -- Начинаем после первой запятой
        INSTR(city_ids, ',', 1, depth) - INSTR(city_ids, ',', 1, 1) - 1  -- До последней запятой
      )
    ELSE NULL
  END as "Промежуточные ID городов",
  path as "Полный ID путь"
FROM paths
WHERE current_city_id = 2
ORDER BY distance, depth;