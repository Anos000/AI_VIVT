-- МАКСИМАЛЬНЫЙ поиск всех возможных маршрутов
WITH paths (current_city_id, path, distance, depth, visited, city_names) AS (
  SELECT 
    1, 
    '1', 
    0, 
    0,
    '1',
    'Москва'
  FROM dual
  
  UNION ALL
  
  SELECT 
    cp.to_city_id,
    p.path || '->' || cp.to_city_id,
    p.distance + cp.dist_km,
    p.depth + 1,
    p.visited || ',' || cp.to_city_id,
    p.city_names || ' → ' || (SELECT name FROM city WHERE id = cp.to_city_id)
  FROM paths p
  JOIN v_city_path_dir cp ON p.current_city_id = cp.from_city_id
  WHERE p.depth < 10  -- Еще больше глубина
    AND INSTR(',' || p.visited || ',', ',' || cp.to_city_id || ',') = 0
)
SELECT 
  city_names as "Полный маршрут",
  distance as "Общее расстояние",
  depth as "Пересадок",
  -- Дополнительная информация о маршруте
  (depth - 1) as "Промежуточных городов",
  ROUND(distance / NULLIF(depth, 0), 2) as "Среднее расстояние между городами"
FROM paths
WHERE current_city_id = 2
ORDER BY distance, depth;