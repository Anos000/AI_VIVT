CREATE TABLE route (
    id            INT PRIMARY KEY,
    route_name    VARCHAR(255) NOT NULL,
    start_city_id INT NOT NULL,
    end_city_id   INT NOT NULL,
    FOREIGN KEY (start_city_id) REFERENCES city(id),
    FOREIGN KEY (end_city_id)   REFERENCES city(id)
)

-- =========================	
-- 12 маршрутов (3×4 категории)
-- =========================

-- Быстрые (FAST)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(1,  'Москва — Санкт-Петербург', 1, 2)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(2,  'Екатеринбург — Челябинск', 6, 14)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(3,  'Ростов-на-Дону — Сочи',    8, 26)

-- Премиальные (PREMIUM)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(4,  'Москва — Казань',          1, 3)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(5,  'Санкт-Петербург — Калининград', 2, 23)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(6,  'Новосибирск — Красноярск', 5, 13)

-- Бюджетные (BUDGET)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(7,  'Самара — Саратов',         7, 20)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(8,  'Воронеж — Белгород',       15, 25)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(9,  'Омск — Томск',             12, 21)

-- Интересные (INTERESTING)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(10, 'Москва — Владивосток',     1, 11)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(11, 'Казань — Сочи',            3, 26)
INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(12, 'Ярославль — Нижний Новгород', 24, 4)

INSERT INTO route (id, route_name, start_city_id, end_city_id) VALUES
(1,  'Москва — Санкт-Петербург', 1, 2),
(2,  'Екатеринбург — Челябинск', 6, 14),
(3,  'Ростов-на-Дону — Сочи',    8, 26),
(4,  'Москва — Казань',          1, 3),
(5,  'Санкт-Петербург — Калининград', 2, 23),
(6,  'Новосибирск — Красноярск', 5, 13),
(7,  'Самара — Саратов',         7, 20),
(8,  'Воронеж — Белгород',       15, 25),
(9,  'Омск — Томск',             12, 21),
(10, 'Москва — Владивосток',     1, 11),
(11, 'Казань — Сочи',            3, 26),
(12, 'Ярославль — Нижний Новгород', 24, 4)