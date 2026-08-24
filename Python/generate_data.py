#!/usr/bin/env python3
"""
generate_data.py
-----------------
FIX rispetto alla versione precedente: la guida del progetto (punto 2)
richiede che i dataset 75/50/25% siano OTTENUTI PER ESTRAZIONE dal
dataset 100%, non generati in modo indipendente. Prima ogni dataset
veniva generato da capo con la stessa sequenza random che avanzava nel
ciclo: risultato, 4 popolazioni diverse invece di 4 sottoinsiemi annidati.

Qui si genera UNA SOLA VOLTA il dataset master (100%), e i dataset più
piccoli vengono ricavati campionando un sottoinsieme di voli dal master
e facendo discendere a cascata posti/prenotazioni/passeggeri coinvolti.
Così una query sul dataset 25% restituisce dati che sono realmente
un pezzo di quelli del 100%, non un campione statisticamente simile
ma diverso.

Airports/Airlines restano identici in tutti i dataset (dati di
riferimento, come da nota nella guida "il risultato informativo di una
query dovrà essere lo stesso in entrambi i DBMS": qui serve la stessa
logica anche tra dataset di taglia diversa).
"""
import csv
import os
import random
from datetime import datetime, timedelta
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Dimensioni del dataset MASTER (100%). Alza questi valori per
# "stressare" l'hardware come richiesto dalla guida, in base alle
# capacita' del tuo computer.
MASTER_FLIGHTS = 4000
MASTER_PASSENGERS = 40000

AIRPORTS_COUNT = 50
AIRLINES_COUNT = 20
SEATS_PER_FLIGHT = 150
OCCUPANCY_RATE = 0.8

DATASET_FRACTIONS = [('100', 1.00), ('75', 0.75), ('50', 0.50), ('25', 0.25)]


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def generate_airports(n):
    return [{
        'code': f'AP{i:03d}',
        'name': f'{fake.city()} Airport',
        'city': fake.city(),
        'country': fake.country()
    } for i in range(n)]


def generate_airlines(n):
    return [{
        'code': f'AL{i:03d}',
        'name': f'{fake.company()} Airlines',
        'country': fake.country()
    } for i in range(n)]


def generate_passengers(n):
    return [{
        'id': i + 1,
        'name': fake.last_name(),
        'first_name': fake.first_name(),
        'passport': fake.bothify(text='??######', letters='ABCDEFGHIJKLMNOPQRSTUVWXYZ'),
        'email': fake.email()
    } for i in range(n)]


def generate_flights(n, airports, airlines, airline_hub):
    flights = []
    statuses = ['SCHEDULED', 'DELAYED', 'CANCELLED', 'COMPLETED']
    base_date = datetime(2024, 1, 1)
    for i in range(n):
        airline = random.choice(airlines)
        if random.random() < 0.5:
            dep = next(a for a in airports if a['code'] == airline_hub[airline['code']])
        else:
            dep = random.choice(airports)
        arr = random.choice(airports)
        while arr == dep:
            arr = random.choice(airports)
        dep_date = base_date + timedelta(
            days=random.randint(0, 364),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )
        duration = timedelta(hours=random.randint(1, 12), minutes=random.randint(0, 59))
        arr_date = dep_date + duration
        flights.append({
            'id': i + 1,
            'number': f"{airline['code']}{random.randint(100, 999)}",
            'departure_date': dep_date.isoformat(),
            'arrival_date': arr_date.isoformat(),
            'status': random.choice(statuses),
            'departure_airport': dep['code'],
            'arrival_airport': arr['code'],
            'airline_code': airline['code']
        })
    return flights


def generate_seats(flights):
    seats = []
    sid = 1
    for flight in flights:
        for row in range(1, 51):
            for col in ['A', 'B', 'C']:
                cls = 'FIRST' if row <= 5 else ('BUSINESS' if row <= 15 else 'ECONOMY')
                seats.append({
                    'id': sid,
                    'number': f'{row}{col}',
                    'class': cls,
                    'status': 'AVAILABLE',
                    'flight_id': flight['id']
                })
                sid += 1
    return seats


def generate_reservations(flights, seats, passengers):
    reservations = []
    rid = 1
    seats_by_flight = {}
    for s in seats:
        seats_by_flight.setdefault(s['flight_id'], []).append(s)
    for flight in flights:
        flight_seats = seats_by_flight[flight['id']]
        n_reserved = int(len(flight_seats) * OCCUPANCY_RATE)
        chosen = random.sample(flight_seats, n_reserved)
        for seat in chosen:
            passenger = random.choice(passengers)
            base_price = 1000 if seat['class'] == 'FIRST' else (500 if seat['class'] == 'BUSINESS' else 150)
            price = base_price + random.randint(-50, 50)
            dep = datetime.fromisoformat(flight['departure_date'])
            res_date = dep - timedelta(days=random.randint(1, 60))
            reservations.append({
                'id': rid,
                'reservation_date': res_date.isoformat(),
                'status': 'CONFIRMED',
                'total_price': price,
                'passenger_id': passenger['id'],
                'flight_id': flight['id'],
                'seat_id': seat['id']
            })
            rid += 1
    return reservations


def write_csv(path, filename, rows, fieldnames):
    with open(os.path.join(path, filename), 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def flights_to_rows(flight_ids, seats_by_flight, reservations_by_flight, passengers_by_id):
    """Dati un insieme di flight_id, ricostruisce le righe di
    seats/reservations/passengers coinvolte (discesa a cascata)."""
    sub_seats = [s for fid in flight_ids for s in seats_by_flight.get(fid, [])]
    sub_reservations = [r for fid in flight_ids for r in reservations_by_flight.get(fid, [])]
    sub_passenger_ids = {r['passenger_id'] for r in sub_reservations}
    sub_passengers = [passengers_by_id[pid] for pid in sub_passenger_ids]
    return sub_seats, sub_reservations, sub_passengers


def main():
    ensure_dir(DATA_DIR)
    airports = generate_airports(AIRPORTS_COUNT)
    airlines = generate_airlines(AIRLINES_COUNT)
    airline_hub = {al['code']: airports[i % len(airports)]['code'] for i, al in enumerate(airlines)}

    print("Generazione dataset MASTER (100%) ...")
    passengers = generate_passengers(MASTER_PASSENGERS)
    flights = generate_flights(MASTER_FLIGHTS, airports, airlines, airline_hub)
    seats = generate_seats(flights)
    reservations = generate_reservations(flights, seats, passengers)
    print(f"  Voli: {len(flights)}, Passeggeri (pool): {len(passengers)}, "
          f"Posti: {len(seats)}, Prenotazioni: {len(reservations)}")

    # Indici di supporto per estrarre i sottoinsiemi in modo efficiente
    seats_by_flight = {}
    for s in seats:
        seats_by_flight.setdefault(s['flight_id'], []).append(s)
    reservations_by_flight = {}
    for r in reservations:
        reservations_by_flight.setdefault(r['flight_id'], []).append(r)
    passengers_by_id = {p['id']: p for p in passengers}

    # Campionamento A CATENA: 75% viene estratto dal 100%, 50% viene
    # estratto dal SOTTOINSIEME 75% (non dal master), 25% dal 50%.
    # Cosi' si ottiene un vero annidamento 25% ⊂ 50% ⊂ 75% ⊂ 100%,
    # non solo quattro estrazioni indipendenti dalla stessa sorgente.
    total_master = len(flights)
    current_flights = flights

    for pct, fraction in DATASET_FRACTIONS:
        print(f"Estrazione dataset {pct}% ...")
        ds_path = os.path.join(DATA_DIR, pct)
        ensure_dir(ds_path)

        if fraction >= 1.0:
            sub_flights = current_flights
        else:
            target_n = max(1, round(total_master * fraction))
            sub_flights = random.sample(current_flights, target_n)
        current_flights = sub_flights  # il livello successivo pesca da qui

        sub_flight_ids = {f['id'] for f in sub_flights}
        # NB: i passeggeri inclusi sono solo quelli referenziati da una
        # prenotazione in questo sottoinsieme. Dato che il pool di 40.000
        # passeggeri viene ripescato con ripetizione da centinaia di
        # migliaia di prenotazioni, anche il 25% dei voli copre gia' la
        # maggior parte del pool: i passeggeri si comportano come un
        # bacino di riferimento (come Airport/Airline), non come una
        # tabella che si riduce linearmente. Voli/posti/prenotazioni
        # invece scalano esattamente con la percentuale richiesta.
        sub_seats, sub_reservations, sub_passengers = flights_to_rows(
            sub_flight_ids, seats_by_flight, reservations_by_flight, passengers_by_id
        )

        write_csv(ds_path, 'airports.csv', airports, ['code', 'name', 'city', 'country'])
        write_csv(ds_path, 'airlines.csv', airlines, ['code', 'name', 'country'])
        write_csv(ds_path, 'passengers.csv', sub_passengers,
                  ['id', 'name', 'first_name', 'passport', 'email'])
        write_csv(ds_path, 'flights.csv', sub_flights,
                  ['id', 'number', 'departure_date', 'arrival_date', 'status',
                   'departure_airport', 'arrival_airport', 'airline_code'])
        write_csv(ds_path, 'seats.csv', sub_seats,
                  ['id', 'number', 'class', 'status', 'flight_id'])
        write_csv(ds_path, 'reservations.csv', sub_reservations,
                  ['id', 'reservation_date', 'status', 'total_price',
                   'passenger_id', 'flight_id', 'seat_id'])

        print(f"  Voli: {len(sub_flights)}, Passeggeri: {len(sub_passengers)}, "
              f"Posti: {len(sub_seats)}, Prenotazioni: {len(sub_reservations)}")


if __name__ == '__main__':
    main()
