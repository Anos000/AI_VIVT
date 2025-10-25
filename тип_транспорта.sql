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
	
SELECT *
FROM users
INSERT INTO USERS (LOGIN, EMAIL, PASSWORD_HASH, ROLE, VERIFIED_AT)
VALUES ('admin', 'nikita@gmail.com', 'scrypt:32768:8:1$XuMtLpkgeNBEO6c6$1e8ca4734bfca2e244dbd29a51c3452e29a0393cd1ab190714554b0641951da43c5ce4c243168d53f41c0206641a56871e36fea1cd99d426691365cc687308df', 'ADMIN', SYSTIMESTAMP)

ALTER TABLE USERS
  ADD (ROLE VARCHAR2(16) DEFAULT 'CLIENT' NOT NULL)
  
  ALTER TABLE USERS
  ADD CONSTRAINT CK_USERS_ROLE CHECK (ROLE IN ('CLIENT','ADMIN'))
  -- (опционально) индекс, если будем часто фильтровать по роли
CREATE INDEX IX_USERS_ROLE ON USERS(ROLE)