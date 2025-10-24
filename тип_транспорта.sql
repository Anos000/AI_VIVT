CREATE TABLE transport_type (
    id   INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
)

-- Заполнение таблицы категориями поездов:
INSERT INTO transport_type (id, name) VALUES
(1, 'Regular'),
(2, 'Fast'),
(3, 'Premium')

ALTER TABLE transport_type
  ADD (
    speed_kmph   NUMBER(5,1),
    price_per_km NUMBER(6,2)
  )
  
UPDATE transport_type SET speed_kmph = 70,  price_per_km = 2 WHERE id = 1; -- Regular
UPDATE transport_type SET speed_kmph = 160, price_per_km = 6 WHERE id = 2; -- Fast
UPDATE transport_type SET speed_kmph = 120, price_per_km = 15 WHERE id = 3; -- Premium

	SELECT *
	FROM transport_type