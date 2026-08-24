CREATE KEYSPACE IF NOT EXISTS flights_ks
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE flights_ks;

CREATE TABLE IF NOT EXISTS airports (
  code    text PRIMARY KEY,
  name    text,
  city    text,
  country text
);

CREATE TABLE IF NOT EXISTS airlines (
  code    text PRIMARY KEY,
  name    text,
  country text
);

-- Q1: voli per status (1 entità)
CREATE TABLE IF NOT EXISTS flights_by_status (
  status             text,
  flight_id          int,
  number             text,
  departure_date     timestamp,
  arrival_date       timestamp,
  departure_airport  text,
  arrival_airport    text,
  airline_code       text,
  PRIMARY KEY (status, flight_id)
);

-- Q2: prenotazioni di un passeggero (2-3 entità, annidamento)
CREATE TABLE IF NOT EXISTS reservations_by_passenger (
  passenger_id       int,
  reservation_id     int,
  flight_number      text,
  departure_date     timestamp,
  arrival_date       timestamp,
  flight_status      text,
  reservation_status text,
  total_price        decimal,
  PRIMARY KEY (passenger_id, reservation_id)
);

-- Q3: prenotazioni per compagnia in intervallo date (4-5 entità)
CREATE TABLE IF NOT EXISTS reservations_by_airline_date (
  airline_code     text,
  departure_date   timestamp,
  reservation_id   int,
  passenger_name   text,
  passenger_email  text,
  flight_number    text,
  seat_number      text,
  seat_class       text,
  total_price      decimal,
  PRIMARY KEY (airline_code, departure_date, reservation_id)
) WITH CLUSTERING ORDER BY (departure_date DESC);

-- Q4: aggregazione per compagnia + aeroporto + periodo (tutte le entità)
-- NOTA: ho aggiunto departure_date come clustering column per il filtro range
CREATE TABLE IF NOT EXISTS reservations_by_airline_airport (
  airline_code      text,
  departure_airport text,
  departure_date    timestamp,
  reservation_id    int,
  total_price       decimal,
  PRIMARY KEY ((airline_code, departure_airport), departure_date, reservation_id)
) WITH CLUSTERING ORDER BY (departure_date DESC);
