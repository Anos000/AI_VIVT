-- УНИВЕРСАЛЬНАЯ ПРОВЕРКА ВСЕХ ПУТЕЙ ВСЕХ МАРШРУТОВ
WITH route_paths (route_id, current_city_id, path, distance, depth, visited, city_names, end_city_id) AS (
  -- Базовый случай: начинаем из начального города каждого маршрута
  SELECT 
    r.id,
    r.start_city_id, 
    CAST(r.start_city_id AS VARCHAR2(1000)), 
    0, 
    0,
    CAST(r.start_city_id AS VARCHAR2(1000)),
    (SELECT name FROM city WHERE id = r.start_city_id),
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
    p.end_city_id
  FROM route_paths p
  JOIN v_city_path_dir cp ON p.current_city_id = cp.from_city_id
  WHERE p.depth < 8
    AND INSTR(',' || p.visited || ',', ',' || cp.to_city_id || ',') = 0
    AND p.current_city_id != p.end_city_id
),
completed_paths AS (
  SELECT 
    rp.route_id,
    rp.path,
    rp.city_names,
    rp.distance,
    rp.depth,
    r.route_name
  FROM route_paths rp
  JOIN route r ON rp.route_id = r.id
  WHERE rp.current_city_id = rp.end_city_id
),
path_segments AS (
  SELECT 
    cp.route_id,
    cp.route_name,
    cp.path as full_path,
    cp.city_names,
    cp.distance,
    cp.depth,
    REGEXP_SUBSTR(cp.path, '(\d+)->(\d+)', 1, LEVEL, NULL, 1) as from_city_id,
    REGEXP_SUBSTR(cp.path, '(\d+)->(\d+)', 1, LEVEL, NULL, 2) as to_city_id,
    LEVEL as segment_number
  FROM completed_paths cp
  CONNECT BY LEVEL <= REGEXP_COUNT(cp.path, '->')
    AND PRIOR cp.path = cp.path
    AND PRIOR SYS_GUID() IS NOT NULL
),
segment_validation AS (
  SELECT 
    ps.route_id,
    ps.route_name,
    ps.full_path,
    ps.city_names,
    ps.distance,
    ps.depth,
    ps.segment_number,
    ps.from_city_id,
    c1.name as from_city_name,
    ps.to_city_id,
    c2.name as to_city_name,
    CASE 
      WHEN cp.edge_id IS NOT NULL THEN '✅ Связь есть'
      ELSE '❌ Связи нет'
    END as connection_status,
    cp.dist_km as segment_distance,
    CASE 
      WHEN cp.edge_id IS NOT NULL THEN 1
      ELSE 0
    END as is_valid
  FROM path_segments ps
  JOIN city c1 ON ps.from_city_id = c1.id
  JOIN city c2 ON ps.to_city_id = c2.id
  LEFT JOIN city_path cp ON (cp.city_a_id = ps.from_city_id AND cp.city_b_id = ps.to_city_id)
                        OR (cp.city_a_id = ps.to_city_id AND cp.city_b_id = ps.from_city_id)
)
SELECT 
  sv.route_name as "Маршрут",
  sv.city_names as "Путь",
  sv.distance as "Расстояние (км)",
  sv.depth as "Пересадок",
  sv.full_path as "ID путь",
  sv.segment_number as "Сегмент",
  sv.from_city_name || ' -> ' || sv.to_city_name as "Переход",
  sv.connection_status as "Статус связи",
  sv.segment_distance as "Расстояние сегмента"
FROM segment_validation sv
ORDER BY 
  sv.route_id,
  sv.full_path,
  sv.segment_number;