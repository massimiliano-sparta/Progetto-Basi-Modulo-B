#!/usr/bin/env python3
import os
import time
import pandas as pd
from neo4j import GraphDatabase
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent
import argparse

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "password123")
CASSANDRA_HOSTS = ['localhost']
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

def clear_neo4j():
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with driver.session() as session:
        # FIX: "MATCH (n) DETACH DELETE n" su un grafo con oltre un milione
        # di nodi e ~2 milioni di relazioni (il dataset 100% gia' caricato)
        # prova a cancellare tutto in un'unica transazione enorme: con
        # 2GB di heap questo puo' saturare la memoria e far cadere la
        # connessione, che e' esattamente il "defunct connection" /
        # TimeoutError che si vede in console. "IN TRANSACTIONS OF N ROWS"
        # (nativo da Neo4j 4.4+, non serve APOC) cancella a lotti lato
        # server, ogni lotto in una sotto-transazione separata.
        session.run("""
            MATCH (n)
            CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS
        """)
    driver.close()
    print("  Neo4j pulito.")

def clear_cassandra():
    cluster = Cluster(CASSANDRA_HOSTS, port=9042)
    session = cluster.connect('flights_ks')
    for t in ['flights_by_status', 'reservations_by_passenger',
              'reservations_by_airline_date', 'reservations_by_airline_airport',
              'airports', 'airlines']:
        try:
            session.execute(f"TRUNCATE {t}")
        except Exception as e:
            print(f"  Warning truncate {t}: {e}")
    cluster.shutdown()
    print("  Cassandra pulita.")

def insert_neo4j_dataset(ds_path):
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    airports = pd.read_csv(os.path.join(ds_path, 'airports.csv'))
    airlines = pd.read_csv(os.path.join(ds_path, 'airlines.csv'))
    passengers = pd.read_csv(os.path.join(ds_path, 'passengers.csv'))
    flights = pd.read_csv(os.path.join(ds_path, 'flights.csv'))
    seats = pd.read_csv(os.path.join(ds_path, 'seats.csv'))
    reservations = pd.read_csv(os.path.join(ds_path, 'reservations.csv'))

    with driver.session() as session:
        batch = airports.to_dict('records')
        for i in range(0, len(batch), 1000):
            session.run("""
                UNWIND $batch as row
                MERGE (a:Airport {code: row.code})
                SET a.name = row.name, a.city = row.city, a.country = row.country
            """, batch=batch[i:i+1000])

        batch = airlines.to_dict('records')
        for i in range(0, len(batch), 1000):
            session.run("""
                UNWIND $batch as row
                MERGE (a:Airline {code: row.code})
                SET a.name = row.name, a.country = row.country
            """, batch=batch[i:i+1000])

        batch = passengers.to_dict('records')
        for i in range(0, len(batch), 1000):
            session.run("""
                UNWIND $batch as row
                MERGE (p:Passenger {id: toInteger(row.id)})
                SET p.name = row.name, p.first_name = row.first_name,
                    p.passport = row.passport, p.email = row.email
            """, batch=batch[i:i+1000])

        batch = flights.to_dict('records')
        for i in range(0, len(batch), 1000):
            session.run("""
                UNWIND $batch as row
                MERGE (f:Flight {id: toInteger(row.id)})
                SET f.number = row.number,
                    f.departure_date = datetime(row.departure_date),
                    f.arrival_date = datetime(row.arrival_date),
                    f.status = row.status
                WITH f, row
                MATCH (dep:Airport {code: row.departure_airport})
                MATCH (arr:Airport {code: row.arrival_airport})
                MATCH (al:Airline {code: row.airline_code})
                MERGE (f)-[:DEPARTS_FROM]->(dep)
                MERGE (f)-[:ARRIVES_AT]->(arr)
                MERGE (f)-[:OPERATED_BY]->(al)
            """, batch=batch[i:i+1000])

        batch = seats.to_dict('records')
        for i in range(0, len(batch), 10000):
            session.run("""
                UNWIND $batch as row
                MERGE (s:Seat {id: toInteger(row.id)})
                SET s.number = row.number, s.class = row.class, s.status = row.status
                WITH s, row
                MATCH (f:Flight {id: toInteger(row.flight_id)})
                MERGE (s)-[:BELONGS_TO]->(f)
            """, batch=batch[i:i+10000])

        batch = reservations.to_dict('records')
        for i in range(0, len(batch), 10000):
            session.run("""
                UNWIND $batch as row
                MERGE (r:Reservation {id: toInteger(row.id)})
                SET r.reservation_date = datetime(row.reservation_date),
                    r.status = row.status,
                    r.total_price = toFloat(row.total_price)
                WITH r, row
                MATCH (p:Passenger {id: toInteger(row.passenger_id)})
                MATCH (f:Flight {id: toInteger(row.flight_id)})
                MATCH (s:Seat {id: toInteger(row.seat_id)})
                MERGE (p)-[:MAKES]->(r)
                MERGE (r)-[:FOR_FLIGHT]->(f)
                MERGE (r)-[:FOR_SEAT]->(s)
            """, batch=batch[i:i+10000])

    driver.close()
    print("  Neo4j completato.")

def insert_cassandra_dataset(ds_path):
    cluster = Cluster(CASSANDRA_HOSTS, port=9042)
    session = cluster.connect('flights_ks')
    session.default_timeout = 60

    airports = pd.read_csv(os.path.join(ds_path, 'airports.csv'))
    airlines = pd.read_csv(os.path.join(ds_path, 'airlines.csv'))
    passengers = pd.read_csv(os.path.join(ds_path, 'passengers.csv'))
    flights = pd.read_csv(os.path.join(ds_path, 'flights.csv'))
    seats = pd.read_csv(os.path.join(ds_path, 'seats.csv'))
    reservations = pd.read_csv(os.path.join(ds_path, 'reservations.csv'))

    for df in [flights, reservations]:
        for col in ['departure_date', 'arrival_date', 'reservation_date']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])

    # Rinomina colonne per evitare conflitti nei merge
    res = reservations.rename(columns={'id': 'reservation_id', 'status': 'reservation_status'})
    fl = flights.rename(columns={'id': 'flight_id', 'status': 'flight_status'})
    pas = passengers.rename(columns={'id': 'passenger_id'})
    se = seats.rename(columns={'id': 'seat_id', 'number': 'seat_number', 'class': 'seat_class'})

    ps_airports = session.prepare("INSERT INTO airports (code, name, city, country) VALUES (?, ?, ?, ?)")
    ps_airlines = session.prepare("INSERT INTO airlines (code, name, country) VALUES (?, ?, ?)")
    ps_fbs = session.prepare("""
        INSERT INTO flights_by_status (status, flight_id, number, departure_date, arrival_date, departure_airport, arrival_airport, airline_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """)
    ps_rbp = session.prepare("""
        INSERT INTO reservations_by_passenger (passenger_id, reservation_id, flight_number, departure_date, arrival_date, flight_status, reservation_status, total_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """)
    ps_rbad = session.prepare("""
        INSERT INTO reservations_by_airline_date (airline_code, departure_date, reservation_id, passenger_name, passenger_email, flight_number, seat_number, seat_class, total_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """)
    ps_rbaa = session.prepare("""
        INSERT INTO reservations_by_airline_airport (airline_code, departure_airport, departure_date, reservation_id, total_price)
        VALUES (?, ?, ?, ?, ?)
    """)

    def load_table(label, batch, chunk_size=1000):
        """Esegue l'inserimento a chunk stampando un log di avanzamento,
        cosi' non si resta col terminale muto per minuti."""
        t0 = time.perf_counter()
        n = len(batch)
        for i in range(0, n, chunk_size):
            execute_concurrent(session, batch[i:i + chunk_size])
            done = min(i + chunk_size, n)
            print(f"    {label}: {done}/{n} righe inserite", end='\r')
        elapsed = time.perf_counter() - t0
        print(f"    {label}: {n}/{n} righe inserite ({elapsed:.1f}s)          ")

    print("  Inserimento airports/airlines...")
    batch = [(ps_airports, tuple(r)) for r in airports[['code', 'name', 'city', 'country']].values]
    load_table('airports', batch, 500)

    batch = [(ps_airlines, tuple(r)) for r in airlines[['code', 'name', 'country']].values]
    load_table('airlines', batch, 500)

    # FIX PERFORMANCE: .iterrows() e' notoriamente lento (crea una Series
    # per riga, in puro Python). Su 480.000 prenotazioni, ripetuto tre
    # volte (rbp/rbad/rbaa), poteva richiedere 10-20 minuti solo per
    # costruire le liste, prima ancora di toccare Cassandra. .itertuples()
    # e' un ordine di grandezza piu' veloce perche' restituisce namedtuple
    # invece di Series.
    print("  Inserimento flights_by_status...")
    batch = [(ps_fbs, (row.status, int(row.id), row.number, row.departure_date, row.arrival_date,
                        row.departure_airport, row.arrival_airport, row.airline_code))
              for row in flights.itertuples(index=False)]
    load_table('flights_by_status', batch)

    # reservations_by_passenger
    print("  Inserimento reservations_by_passenger...")
    rbp = res.merge(fl[['flight_id', 'number', 'departure_date', 'arrival_date', 'flight_status']],
                     left_on='flight_id', right_on='flight_id')
    batch = [(ps_rbp, (int(row.passenger_id), int(row.reservation_id), row.number,
                        row.departure_date, row.arrival_date, row.flight_status,
                        row.reservation_status, float(row.total_price)))
              for row in rbp.itertuples(index=False)]
    load_table('reservations_by_passenger', batch)

    # reservations_by_airline_date
    print("  Inserimento reservations_by_airline_date...")
    rbad = res.merge(fl[['flight_id', 'number', 'departure_date', 'airline_code']], left_on='flight_id', right_on='flight_id')
    rbad = rbad.merge(pas[['passenger_id', 'name', 'email']], left_on='passenger_id', right_on='passenger_id')
    rbad = rbad.merge(se[['seat_id', 'seat_number', 'seat_class']], left_on='seat_id', right_on='seat_id')
    batch = [(ps_rbad, (row.airline_code, row.departure_date, int(row.reservation_id),
                         row.name, row.email, row.number, row.seat_number, row.seat_class,
                         float(row.total_price)))
              for row in rbad.itertuples(index=False)]
    load_table('reservations_by_airline_date', batch)

    # reservations_by_airline_airport
    print("  Inserimento reservations_by_airline_airport...")
    rbaa = res.merge(fl[['flight_id', 'departure_date', 'airline_code', 'departure_airport']], left_on='flight_id', right_on='flight_id')
    batch = [(ps_rbaa, (row.airline_code, row.departure_airport, row.departure_date,
                         int(row.reservation_id), float(row.total_price)))
              for row in rbaa.itertuples(index=False)]
    load_table('reservations_by_airline_airport', batch)

    cluster.shutdown()
    print("  Cassandra completato.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', required=True, choices=['25','50','75','100'])
    args = parser.parse_args()

    ds_path = os.path.join(DATA_DIR, args.dataset)
    print(f"\n=== Dataset {args.dataset}% ===")
    print("Pulizia DB...")
    clear_neo4j()
    clear_cassandra()
    print("Inserimento Neo4j...")
    insert_neo4j_dataset(ds_path)
    print("Inserimento Cassandra...")
    insert_cassandra_dataset(ds_path)

if __name__ == '__main__':
    main()
