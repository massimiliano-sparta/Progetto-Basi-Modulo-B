#!/usr/bin/env python3
import time
import csv
import statistics
import os
import argparse
from datetime import datetime
from neo4j import GraphDatabase
from cassandra.cluster import Cluster

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "password123")
CASSANDRA_HOSTS = ['localhost']

class FlightBenchmark:
    def __init__(self):
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        self.cassandra_cluster = Cluster(CASSANDRA_HOSTS, port=9042)
        self.cassandra_session = self.cassandra_cluster.connect('flights_ks')

        self.q1_status = 'SCHEDULED'
        self.q2_passenger_id = 1
        self.q3_airline = 'AL001'
        self.q3_start = datetime(2024, 6, 1)
        self.q3_end = datetime(2024, 6, 30)
        self.q4_airline = 'AL001'
        self.q4_airport = 'AP001'
        self.q4_start = datetime(2024, 1, 1)
        self.q4_end = datetime(2024, 6, 30)

        self.cass_q1 = self.cassandra_session.prepare("SELECT * FROM flights_by_status WHERE status = ?")
        self.cass_q2 = self.cassandra_session.prepare("SELECT * FROM reservations_by_passenger WHERE passenger_id = ?")
        self.cass_q3 = self.cassandra_session.prepare("SELECT * FROM reservations_by_airline_date WHERE airline_code = ? AND departure_date >= ? AND departure_date <= ?")
        self.cass_q4 = self.cassandra_session.prepare("SELECT count(*) as cnt, sum(total_price) as revenue FROM reservations_by_airline_airport WHERE airline_code = ? AND departure_airport = ? AND departure_date >= ? AND departure_date <= ?")

    def run_neo4j_q1(self):
        # FIX: prima restituiva solo count(f) (uno scalare), mentre la
        # query Cassandra corrispondente (SELECT *) restituisce tutte le
        # righe con tutti i campi. Non erano confrontabili: la guida
        # richiede esplicitamente che "il risultato informativo di una
        # query... dovrà essere lo stesso in entrambi i DBMS" (punto 3).
        # Ora Neo4j attraversa le stesse relazioni necessarie per
        # restituire gli stessi campi presenti in flights_by_status.
        with self.neo4j_driver.session() as session:
            t0 = time.perf_counter()
            result = session.run("""
                MATCH (f:Flight {status: $status})
                MATCH (f)-[:DEPARTS_FROM]->(dep:Airport)
                MATCH (f)-[:ARRIVES_AT]->(arr:Airport)
                MATCH (f)-[:OPERATED_BY]->(al:Airline)
                RETURN f.id AS id, f.number AS number,
                       f.departure_date AS departure_date, f.arrival_date AS arrival_date,
                       f.status AS status, dep.code AS departure_airport,
                       arr.code AS arrival_airport, al.code AS airline_code
            """, status=self.q1_status)
            list(result)
            return (time.perf_counter() - t0) * 1000

    def run_neo4j_q2(self):
        # FIX: mancavano f.arrival_date e f.status rispetto alle colonne
        # restituite da "SELECT * FROM reservations_by_passenger" lato
        # Cassandra (che include arrival_date e flight_status).
        with self.neo4j_driver.session() as session:
            t0 = time.perf_counter()
            result = session.run("""
                MATCH (p:Passenger {id: $pid})-[:MAKES]->(r:Reservation)-[:FOR_FLIGHT]->(f:Flight)
                RETURN r.id AS reservation_id, r.reservation_date AS reservation_date,
                       r.status AS reservation_status, r.total_price AS total_price,
                       f.number AS flight_number, f.departure_date AS departure_date,
                       f.arrival_date AS arrival_date, f.status AS flight_status
            """, pid=self.q2_passenger_id)
            list(result)
            return (time.perf_counter() - t0) * 1000

    def run_neo4j_q3(self):
        with self.neo4j_driver.session() as session:
            t0 = time.perf_counter()
            result = session.run("""
                MATCH (r:Reservation)-[:FOR_FLIGHT]->(f:Flight)-[:OPERATED_BY]->(a:Airline {code: $code})
                WHERE f.departure_date >= datetime($start) AND f.departure_date <= datetime($end)
                MATCH (r)-[:FOR_SEAT]->(s:Seat)
                MATCH (p:Passenger)-[:MAKES]->(r)
                RETURN r.id, p.name, p.email, f.number, s.number, s.class, r.total_price
            """, code=self.q3_airline, start=self.q3_start.isoformat(), end=self.q3_end.isoformat())
            list(result)
            return (time.perf_counter() - t0) * 1000

    def run_neo4j_q4(self):
        with self.neo4j_driver.session() as session:
            t0 = time.perf_counter()
            result = session.run("""
                MATCH (f:Flight)-[:DEPARTS_FROM]->(ap:Airport {code: $airport})
                WHERE f.departure_date >= datetime($start) AND f.departure_date <= datetime($end)
                MATCH (f)-[:OPERATED_BY]->(a:Airline {code: $code})
                MATCH (r:Reservation)-[:FOR_FLIGHT]->(f)
                RETURN count(r) as cnt, sum(r.total_price) as revenue
            """, airport=self.q4_airport, start=self.q4_start.isoformat(),
                 end=self.q4_end.isoformat(), code=self.q4_airline)
            result.single()
            return (time.perf_counter() - t0) * 1000

    def run_cassandra_q1(self):
        t0 = time.perf_counter()
        self.cassandra_session.execute(self.cass_q1, [self.q1_status])
        return (time.perf_counter() - t0) * 1000

    def run_cassandra_q2(self):
        t0 = time.perf_counter()
        self.cassandra_session.execute(self.cass_q2, [self.q2_passenger_id])
        return (time.perf_counter() - t0) * 1000

    def run_cassandra_q3(self):
        t0 = time.perf_counter()
        self.cassandra_session.execute(self.cass_q3, [self.q3_airline, self.q3_start, self.q3_end])
        return (time.perf_counter() - t0) * 1000

    def run_cassandra_q4(self):
        t0 = time.perf_counter()
        self.cassandra_session.execute(self.cass_q4, [self.q4_airline, self.q4_airport, self.q4_start, self.q4_end])
        return (time.perf_counter() - t0) * 1000

    def run_series(self, db, qname, n=31):
        runner = getattr(self, f'run_{db}_{qname}')
        times = []
        for i in range(n):
            t = runner()
            times.append(t)
            if i == 0:
                print(f"    {db} {qname} first: {t:.2f} ms")
        return times[0], times[1:]

    def benchmark_dataset(self, ds_name):
        results = []
        for db in ['neo4j', 'cassandra']:
            for q in ['q1', 'q2', 'q3', 'q4']:
                print(f"  Esecuzione {db} {q} ...")
                first, rest = self.run_series(db, q, 31)
                avg = statistics.mean(rest)
                stdev = statistics.stdev(rest) if len(rest) > 1 else 0
                results.append({
                    'dataset': ds_name,
                    'dbms': db,
                    'query': q,
                    'first_ms': round(first, 3),
                    'avg_ms': round(avg, 3),
                    'stdev_ms': round(stdev, 3)
                })
        return results

    def close(self):
        self.neo4j_driver.close()
        self.cassandra_cluster.shutdown()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', required=True, choices=['25','50','75','100'])
    parser.add_argument('--output', default='benchmark_results.csv')
    parser.add_argument('--append', action='store_true')
    args = parser.parse_args()

    bench = FlightBenchmark()
    print(f"\n=== Benchmark dataset {args.dataset}% ===")
    results = bench.benchmark_dataset(args.dataset)
    bench.close()

    mode = 'a' if args.append else 'w'
    header = not (args.append and os.path.exists(args.output))
    with open(args.output, mode, newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['dataset', 'dbms', 'query', 'first_ms', 'avg_ms', 'stdev_ms'])
        if header:
            writer.writeheader()
        writer.writerows(results)
    print(f"Risultati salvati in {args.output}")

if __name__ == '__main__':
    main()
