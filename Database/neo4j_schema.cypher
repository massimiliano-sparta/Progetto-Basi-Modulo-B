// ============================================================
// Schema Neo4j — Flight Reservation System
// ============================================================
// Modello a grafo (property graph). Nodi:
//   Airport, Airline, Flight, Seat, Passenger, Reservation
//
// Reservation è modellata come NODO (non come semplice relazione)
// perché lega tre entità (Passenger, Flight, Seat): è una relazione
// ternaria, e le relazioni ternarie in un grafo si rappresentano
// bene con un nodo intermedio ("relazione reificata").
//
// Relazioni:
//   (:Passenger)-[:MAKES]->(:Reservation)
//   (:Reservation)-[:FOR_FLIGHT]->(:Flight)
//   (:Reservation)-[:FOR_SEAT]->(:Seat)
//   (:Seat)-[:BELONGS_TO]->(:Flight)
//   (:Flight)-[:DEPARTS_FROM]->(:Airport)
//   (:Flight)-[:ARRIVES_AT]->(:Airport)
//   (:Flight)-[:OPERATED_BY]->(:Airline)
// ============================================================

// --- Vincoli di unicità (creano anche un indice implicito) ---
CREATE CONSTRAINT flight_id       IF NOT EXISTS FOR (f:Flight)      REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT passenger_id    IF NOT EXISTS FOR (p:Passenger)   REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT airport_code    IF NOT EXISTS FOR (a:Airport)     REQUIRE a.code IS UNIQUE;
CREATE CONSTRAINT airline_code    IF NOT EXISTS FOR (a:Airline)     REQUIRE a.code IS UNIQUE;
CREATE CONSTRAINT seat_id         IF NOT EXISTS FOR (s:Seat)        REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT reservation_id  IF NOT EXISTS FOR (r:Reservation) REQUIRE r.id IS UNIQUE;

// --- Indici sui campi usati nei filtri delle 4 query di benchmark ---
CREATE INDEX flight_status         IF NOT EXISTS FOR (f:Flight)      ON (f.status);
CREATE INDEX flight_departure_date IF NOT EXISTS FOR (f:Flight)      ON (f.departure_date);
CREATE INDEX reservation_date      IF NOT EXISTS FOR (r:Reservation) ON (r.reservation_date);

// ============================================================
// Esempio di inserimento (una riga, per riferimento — l'inserimento
// vero e proprio va fatto in batch da scripts/insert_neo4j.py con
// UNWIND, molto più efficiente di una MERGE per riga)
// ============================================================
// MERGE (a:Airport {code: $dep_code})
// MERGE (b:Airport {code: $arr_code})
// MERGE (al:Airline {code: $airline_code})
// MERGE (f:Flight {id: $flight_id})
//   SET f.number = $number, f.departure_date = datetime($dep_date),
//       f.arrival_date = datetime($arr_date), f.status = $status
// MERGE (f)-[:DEPARTS_FROM]->(a)
// MERGE (f)-[:ARRIVES_AT]->(b)
// MERGE (f)-[:OPERATED_BY]->(al)
