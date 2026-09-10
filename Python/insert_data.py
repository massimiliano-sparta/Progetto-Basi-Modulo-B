#!/usr/bin/env python3
# ============================================================================
# INSERT_DATA.PY — Il "camion delle consegne" del progetto
# ----------------------------------------------------------------------------
# Questo script prende i dati grezzi (file .csv con aeroporti, compagnie,
# passeggeri, voli, posti, prenotazioni) e li carica dentro Neo4j e dentro
# Cassandra, uno alla volta, per ogni "taglia" di dataset (25%, 50%, 75%,
# 100% dei dati totali). Prima di ogni caricamento, pulisce completamente i
# due database, così ogni test parte sempre da zero.
# ============================================================================
 
import os                # Per gestire percorsi di file e cartelle
import time               # Per misurare quanto tempo impiega un inserimento
import pandas as pd       # Libreria per leggere e manipolare tabelle (i file CSV)
from neo4j import GraphDatabase                 # Libreria per parlare con Neo4j
from cassandra.cluster import Cluster           # Libreria per parlare con Cassandra
from cassandra.concurrent import execute_concurrent  # Per inserire più righe insieme, in parallelo
import argparse           # Per leggere le opzioni da riga di comando
 
# --- Parametri di connessione (uguali a benchmark.py) ----------------------
NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "password123")
CASSANDRA_HOSTS = ['localhost']
 
# Calcola automaticamente la cartella "data" che si trova accanto a questo
# script (indipendentemente da dove lo lanci), e dentro cui ci sono le
# sottocartelle 25/, 50/, 75/, 100/ con i file CSV di ciascun dataset.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
 
 
def clear_neo4j():
    """
    Svuota completamente il database Neo4j: cancella TUTTI i nodi (entità,
    es. voli, passeggeri) e TUTTE le relazioni (frecce che li collegano).
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with driver.session() as session:
        # NOTA STORICA (dal commento originale):
        # Un semplice "MATCH (n) DETACH DELETE n" su un grafo enorme (col
        # dataset al 100% ci sono oltre 1 milione di nodi e ~2 milioni di
        # relazioni) prova a cancellare TUTTO in un'unica mega-transazione.
        # Con solo 2GB di memoria assegnata a Neo4j, questo può saturare la
        # memoria e far cadere la connessione (l'errore "defunct connection"
        # / TimeoutError che si vedeva prima in console).
        #
        # La soluzione: "IN TRANSACTIONS OF N ROWS" (disponibile da Neo4j
        # 4.4 in poi, senza bisogno del plugin APOC) dice a Neo4j di
        # cancellare i dati A LOTTI di 10.000 righe alla volta, ognuno in
        # una piccola transazione separata, così la memoria non esplode
        # mai tutta insieme.
        # Sintassi aggiornata: "CALL { WITH n ... }" senza clausola di scope
        # è deprecata dalle versioni recenti di Neo4j (produceva l'avviso
        # FeatureDeprecationWarning nei log). "CALL (n) { ... }" è la forma
        # equivalente e non deprecata, suggerita direttamente da Neo4j.
        session.run("""
            MATCH (n)
            CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS
        """)
    driver.close()
    print("  Neo4j pulito.")
 
 
def clear_cassandra():
    """
    Svuota tutte le tabelle di Cassandra usate dal progetto.
    TRUNCATE è l'equivalente di "cancella tutte le righe di questa tabella,
    ma tieni la struttura (le colonne) pronta per essere riutilizzata".
    """
    cluster = Cluster(CASSANDRA_HOSTS, port=9042)
    session = cluster.connect('flights_ks')
 
    # Elenco di tutte le tabelle che vanno svuotate prima di ogni test
    for t in ['flights_by_status', 'reservations_by_passenger',
              'reservations_by_airline_date', 'reservations_by_airline_airport',
              'airports', 'airlines']:
        try:
            session.execute(f"TRUNCATE {t}")
        except Exception as e:
            # Se una tabella non esiste ancora o c'è un problema, non
            # blocchiamo tutto: stampiamo solo un avviso e andiamo avanti
            print(f"  Warning truncate {t}: {e}")
 
    cluster.shutdown()
    print("  Cassandra pulita.")
 
 
def insert_neo4j_dataset(ds_path):
    """
    Carica in Neo4j tutti i dati di UN dataset (es. la cartella "50/").
    Neo4j rappresenta i dati come un grafo: 'nodi' (es. un volo, un
    passeggero) collegati da 'relazioni' (es. "il volo PARTE DA questo
    aeroporto").
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
 
    # Legge tutti i file CSV del dataset in delle tabelle pandas (DataFrame)
    airports = pd.read_csv(os.path.join(ds_path, 'airports.csv'))
    airlines = pd.read_csv(os.path.join(ds_path, 'airlines.csv'))
    passengers = pd.read_csv(os.path.join(ds_path, 'passengers.csv'))
    flights = pd.read_csv(os.path.join(ds_path, 'flights.csv'))
    seats = pd.read_csv(os.path.join(ds_path, 'seats.csv'))
    reservations = pd.read_csv(os.path.join(ds_path, 'reservations.csv'))
 
    with driver.session() as session:
        # ---- Inserimento AEROPORTI --------------------------------------
        # to_dict('records') trasforma la tabella in una lista di
        # dizionari, es: [{'code': 'AP001', 'name': 'Fiumicino', ...}, ...]
        # così Neo4j può leggerli facilmente con UNWIND (che li "srotola"
        # uno per uno).
        batch = airports.to_dict('records')
 
        # Invece di inserire un aeroporto alla volta (lentissimo), li
        # mandiamo a Neo4j a "pacchetti" (batch) di 1000 righe, per
        # velocizzare e non sovraccaricare la memoria.
        for i in range(0, len(batch), 1000):
            session.run("""
                UNWIND $batch as row
                MERGE (a:Airport {code: row.code})
                SET a.name = row.name, a.city = row.city, a.country = row.country
            """, batch=batch[i:i+1000])
            # MERGE = "se esiste già un nodo Airport con questo codice,
            # riusalo; altrimenti creane uno nuovo" (evita duplicati)
            # SET = imposta/aggiorna le proprietà del nodo
 
        # ---- Inserimento COMPAGNIE AEREE --------------------------------
        batch = airlines.to_dict('records')
        for i in range(0, len(batch), 1000):
            session.run("""
                UNWIND $batch as row
                MERGE (a:Airline {code: row.code})
                SET a.name = row.name, a.country = row.country
            """, batch=batch[i:i+1000])
 
        # ---- Inserimento PASSEGGERI --------------------------------------
        batch = passengers.to_dict('records')
        for i in range(0, len(batch), 1000):
            session.run("""
                UNWIND $batch as row
                MERGE (p:Passenger {id: toInteger(row.id)})
                SET p.name = row.name, p.first_name = row.first_name,
                    p.passport = row.passport, p.email = row.email
            """, batch=batch[i:i+1000])
            # toInteger(...) converte il valore letto dal CSV (che arriva
            # come testo/numero generico) in un intero vero e proprio
 
        # ---- Inserimento VOLI + relazioni con aeroporti e compagnia ------
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
            # Qui, dopo aver creato/aggiornato il nodo Volo, "ricolleghiamo
            # i fili": troviamo l'aeroporto di partenza, quello di arrivo e
            # la compagnia (che devono già esistere, essendo stati inseriti
            # sopra) e creiamo le tre relazioni/frecce che li uniscono al volo.
 
        # ---- Inserimento POSTI (Seat) + relazione col volo ---------------
        batch = seats.to_dict('records')
        # Qui i pacchetti sono più grandi (10000 invece di 1000) perché i
        # posti sono molti di più dei voli, e conviene mandarne di più
        # insieme per non rallentare troppo il processo
        for i in range(0, len(batch), 10000):
            session.run("""
                UNWIND $batch as row
                MERGE (s:Seat {id: toInteger(row.id)})
                SET s.number = row.number, s.class = row.class, s.status = row.status
                WITH s, row
                MATCH (f:Flight {id: toInteger(row.flight_id)})
                MERGE (s)-[:BELONGS_TO]->(f)
            """, batch=batch[i:i+10000])
 
        # ---- Inserimento PRENOTAZIONI + relazioni con passeggero/volo/posto
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
            # Ogni prenotazione viene collegata a: chi l'ha fatta (Passeggero
            # -MAKES-> Prenotazione), a quale volo si riferisce
            # (Prenotazione -FOR_FLIGHT-> Volo) e a quale posto
            # (Prenotazione -FOR_SEAT-> Seat)
 
    driver.close()
    print("  Neo4j completato.")
 
 
def insert_cassandra_dataset(ds_path):
    """
    Carica in Cassandra gli stessi dati, ma con una logica diversa da
    Neo4j: qui NON ci sono relazioni/frecce, invece i dati vengono
    "duplicati" e organizzati in più tabelle, ciascuna pensata per
    rispondere velocemente a UNA query specifica (è il concetto di
    "query-driven design", tipico dei database NoSQL a colonne larghe).
    """
    cluster = Cluster(CASSANDRA_HOSTS, port=9042)
    session = cluster.connect('flights_ks')
    session.default_timeout = 60  # aspetta fino a 60 secondi prima di dire "troppo lento"
 
    # Legge di nuovo tutti i CSV (questa funzione è indipendente da
    # insert_neo4j_dataset, quindi rilegge i file da zero)
    airports = pd.read_csv(os.path.join(ds_path, 'airports.csv'))
    airlines = pd.read_csv(os.path.join(ds_path, 'airlines.csv'))
    passengers = pd.read_csv(os.path.join(ds_path, 'passengers.csv'))
    flights = pd.read_csv(os.path.join(ds_path, 'flights.csv'))
    seats = pd.read_csv(os.path.join(ds_path, 'seats.csv'))
    reservations = pd.read_csv(os.path.join(ds_path, 'reservations.csv'))
 
    # Converte le colonne che contengono date (lette come semplice testo
    # dal CSV) in veri oggetti "data/ora" di Python, altrimenti Cassandra
    # non le accetterebbe nelle colonne di tipo timestamp
    for df in [flights, reservations]:
        for col in ['departure_date', 'arrival_date', 'reservation_date']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
 
    # Rinomina alcune colonne prima di unire le tabelle (fare il "merge"),
    # per evitare che due tabelle abbiano una colonna con lo stesso nome
    # ma significato diverso (es. 'id' e 'status' esistono sia in
    # reservations che in flights: se non li rinominiamo, dopo il merge
    # non sapremmo più quale 'status' appartiene a chi)
    res = reservations.rename(columns={'id': 'reservation_id', 'status': 'reservation_status'})
    fl = flights.rename(columns={'id': 'flight_id', 'status': 'flight_status'})
    pas = passengers.rename(columns={'id': 'passenger_id'})
    se = seats.rename(columns={'id': 'seat_id', 'number': 'seat_number', 'class': 'seat_class'})
 
    # --- Prepara in anticipo tutte le query di INSERIMENTO -------------
    # (stesso concetto delle query "preparate" viste in benchmark.py: più
    # veloce ed è la pratica consigliata da Cassandra)
    ps_airports = session.prepare("INSERT INTO airports (code, name, city, country) VALUES (?, ?, ?, ?)")
    ps_airlines = session.prepare("INSERT INTO airlines (code, name, country) VALUES (?, ?, ?)")
 
    # Questa tabella serve a rispondere velocemente alla Query 1
    # ("dammi tutti i voli con un certo stato")
    ps_fbs = session.prepare("""
        INSERT INTO flights_by_status (status, flight_id, number, departure_date, arrival_date, departure_airport, arrival_airport, airline_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """)
 
    # Questa tabella serve a rispondere velocemente alla Query 2
    # ("dammi tutte le prenotazioni di un passeggero")
    ps_rbp = session.prepare("""
        INSERT INTO reservations_by_passenger (passenger_id, reservation_id, flight_number, departure_date, arrival_date, flight_status, reservation_status, total_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """)
 
    # Questa tabella serve alla Query 3
    # ("dammi le prenotazioni di una compagnia in un periodo, coi dati
    # del passeggero e del posto")
    ps_rbad = session.prepare("""
        INSERT INTO reservations_by_airline_date (airline_code, departure_date, reservation_id, passenger_name, passenger_email, flight_number, seat_number, seat_class, total_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """)
 
    # Questa tabella serve alla Query 4
    # ("quanti biglietti e quanti soldi ha incassato una compagnia da un
    # certo aeroporto in un periodo")
    ps_rbaa = session.prepare("""
        INSERT INTO reservations_by_airline_airport (airline_code, departure_airport, departure_date, reservation_id, total_price)
        VALUES (?, ?, ?, ?, ?)
    """)
 
    def load_table(label, batch, chunk_size=1000):
        """
        Funzione di supporto: inserisce una lista di righe (batch) dentro
        Cassandra a "pacchetti" (chunk), stampando via via l'avanzamento.
        Senza questo log, il terminale resterebbe "muto" per minuti su
        dataset grandi, facendo pensare che lo script si sia bloccato.
        """
        t0 = time.perf_counter()
        n = len(batch)
        for i in range(0, n, chunk_size):
            # execute_concurrent manda tante query di inserimento IN
            # PARALLELO invece che una alla volta in fila: molto più
            # veloce su grandi quantità di dati
            execute_concurrent(session, batch[i:i + chunk_size])
 
            done = min(i + chunk_size, n)
            # end='\r' fa tornare il cursore all'inizio della riga, così
            # il numero di "righe inserite" si aggiorna sul posto invece
            # di stampare mille righe una sotto l'altra
            print(f"    {label}: {done}/{n} righe inserite", end='\r')
 
        elapsed = time.perf_counter() - t0
        print(f"    {label}: {n}/{n} righe inserite ({elapsed:.1f}s)          ")
 
    # ---- Carica AEROPORTI e COMPAGNIE ------------------------------------
    print("  Inserimento airports/airlines...")
    # Ogni elemento di 'batch' è una tupla (query_preparata, valori_da_inserire)
    batch = [(ps_airports, tuple(r)) for r in airports[['code', 'name', 'city', 'country']].values]
    load_table('airports', batch, 500)
 
    batch = [(ps_airlines, tuple(r)) for r in airlines[['code', 'name', 'country']].values]
    load_table('airlines', batch, 500)
 
    # NOTA STORICA (dal commento originale) SULLA PERFORMANCE:
    # .iterrows() è un metodo pandas notoriamente lento, perché per ogni
    # riga della tabella crea un oggetto "Series" (in puro Python, senza
    # ottimizzazioni). Su circa 480.000 prenotazioni, ripetuto per tre
    # volte (una per ciascuna delle tabelle rbp/rbad/rbaa), poteva
    # richiedere 10-20 minuti SOLO per preparare le liste di dati, prima
    # ancora di toccare Cassandra! .itertuples() invece restituisce una
    # "namedtuple" (una struttura leggera) invece di una Series, ed è
    # molto più veloce: un ordine di grandezza in meno.
 
    # ---- Carica flights_by_status (tabella per la Query 1) --------------
    print("  Inserimento flights_by_status...")
    batch = [(ps_fbs, (row.status, int(row.id), row.number, row.departure_date, row.arrival_date,
                        row.departure_airport, row.arrival_airport, row.airline_code))
              for row in flights.itertuples(index=False)]
    load_table('flights_by_status', batch)
 
    # ---- Carica reservations_by_passenger (tabella per la Query 2) ------
    print("  Inserimento reservations_by_passenger...")
    # Prima uniamo (merge, come una JOIN in SQL) le prenotazioni con i
    # dati del volo corrispondente, per avere tutte le colonne che ci
    # servono in un'unica riga
    rbp = res.merge(fl[['flight_id', 'number', 'departure_date', 'arrival_date', 'flight_status']],
                     left_on='flight_id', right_on='flight_id')
    batch = [(ps_rbp, (int(row.passenger_id), int(row.reservation_id), row.number,
                        row.departure_date, row.arrival_date, row.flight_status,
                        row.reservation_status, float(row.total_price)))
              for row in rbp.itertuples(index=False)]
    load_table('reservations_by_passenger', batch)
 
    # ---- Carica reservations_by_airline_date (tabella per la Query 3) ---
    print("  Inserimento reservations_by_airline_date...")
    # Qui servono TRE merge in fila: prenotazioni + voli, poi + passeggeri,
    # poi + posti, per avere in una sola riga tutti i dati richiesti dalla
    # query (compagnia, data, passeggero, posto, prezzo...)
    rbad = res.merge(fl[['flight_id', 'number', 'departure_date', 'airline_code']], left_on='flight_id', right_on='flight_id')
    rbad = rbad.merge(pas[['passenger_id', 'name', 'email']], left_on='passenger_id', right_on='passenger_id')
    rbad = rbad.merge(se[['seat_id', 'seat_number', 'seat_class']], left_on='seat_id', right_on='seat_id')
    batch = [(ps_rbad, (row.airline_code, row.departure_date, int(row.reservation_id),
                         row.name, row.email, row.number, row.seat_number, row.seat_class,
                         float(row.total_price)))
              for row in rbad.itertuples(index=False)]
    load_table('reservations_by_airline_date', batch)
 
    # ---- Carica reservations_by_airline_airport (tabella per la Query 4)
    print("  Inserimento reservations_by_airline_airport...")
    rbaa = res.merge(fl[['flight_id', 'departure_date', 'airline_code', 'departure_airport']], left_on='flight_id', right_on='flight_id')
    batch = [(ps_rbaa, (row.airline_code, row.departure_airport, row.departure_date,
                         int(row.reservation_id), float(row.total_price)))
              for row in rbaa.itertuples(index=False)]
    load_table('reservations_by_airline_airport', batch)
 
    cluster.shutdown()
    print("  Cassandra completato.")
 
 
def main():
    # Legge l'argomento --dataset da riga di comando, es:
    #   python insert_data.py --dataset 100
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', required=True, choices=['25', '50', '75', '100'])
    args = parser.parse_args()
 
    # Costruisce il percorso alla cartella giusta, es. .../data/100
    ds_path = os.path.join(DATA_DIR, args.dataset)
 
    print(f"\n=== Dataset {args.dataset}% ===")
 
    # Step 1: pulizia totale di entrambi i database, per partire "puliti"
    print("Pulizia DB...")
    clear_neo4j()
    clear_cassandra()
 
    # Step 2: caricamento dei dati in Neo4j
    print("Inserimento Neo4j...")
    insert_neo4j_dataset(ds_path)
 
    # Step 3: caricamento degli stessi dati in Cassandra
    print("Inserimento Cassandra...")
    insert_cassandra_dataset(ds_path)
 
 
if __name__ == '__main__':
    main()
 
