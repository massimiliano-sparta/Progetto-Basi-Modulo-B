# Flight Reservation System: Neo4j vs Cassandra

Progetto per il modulo NoSQL del corso di Basi di Dati, Corso di Laurea in Informatica, Università degli Studi di Messina (A.A. 2025/2026).

Confronto sperimentale tra un database a grafo (**Neo4j 5.24**) e un database wide column (**Apache Cassandra 4.1**) sullo stesso caso di studio: un sistema di prenotazione voli. Quattro query di complessità crescente, quattro dataset annidati (25%, 50%, 75%, 100%), 31 esecuzioni per configurazione con intervalli di confidenza al 95% sulla media a regime.

**Autori:** Massimiliano Spartà (matricola 566093) e Simone Adamo (matricola 567317)

## Risultato in breve

| Query | Descrizione | Vince |
|---|---|---|
| Q1 | Voli per stato (1 entità, filtro semplice) | Cassandra |
| Q2 | Prenotazioni di un passeggero (lookup puntuale) | Cassandra |
| Q3 | Prenotazioni per compagnia in un intervallo di date | Cassandra |
| Q4 | Aggregazione per compagnia, aeroporto e periodo | Neo4j |

Cassandra vince su lookup e filtri progettati in anticipo grazie alla denormalizzazione query first. Neo4j vince sull'unica query di aggregazione, perché può ancorarsi a nodi indicizzati e sommare durante il traversal invece di dover trasferire l'intera partizione al client. L'analisi completa, con grafici e intervalli di confidenza per ogni configurazione, è nel report in `PDF/Report_progetto_basi_ultimo.pdf`.

## Struttura del repository

```
.
├── Benchmark/
│   ├── benchmark_results.csv       # Output grezzo di benchmark.py
│   └── results.xlsx
|
├── Database/
│   ├── cassandra_schema.cql        # Keyspace e 4 tabelle denormalizzate
│   └── neo4j_schema.cypher         # Constraint di unicità e indici
|
├── Immagini/                       # Istogrammi generati da analyze_results.py
|
├── Istruzioni_bash/
│   ├── comando_da_sapere.txt
│   ├── istruzioni.sh               # Sequenza manuale dei comandi, passo per passo
│   └── run_experiments.sh          # Pipeline completa: reset container → insert → benchmark → grafici
|
├── PDF/
│   ├── basi_di_dati_nosql-tracce_progetti_2026_published.pdf
│   ├── guida_progetti_basi_di_dati-nosql_2026.pdf
│   └── Report_progetto_basi_ultimo.pdf
|
├── Python/
│   ├── analyze_results.py          # Grafici e riepilogo Excel dai risultati
│   ├── benchmark.py                # 31 esecuzioni per query, cold + warm
│   ├── generate_data.py            # Generazione dataset con Faker (seed=42)
│   └── insert_data.py              # Inserimento batch in Neo4j e Cassandra
|
├── passo_base/
│   └── requirements.txt            # Dipendenze Python
|
└── docker-compose.yml              # Neo4j 5.24 + Cassandra 4.1, risorse comparabili
```

## Requisiti

- Docker e Docker Compose (plugin `docker compose`)
- Python 3.10+
- Circa 4 GB di RAM libera per i due container (2 GB di heap ciascuno)

Dipendenze Python (`passo_base/requirements.txt`):

```
faker==26.0.0
neo4j==5.23.0
cassandra-driver==3.29.1
pandas==2.2.2
matplotlib==3.9.1
scipy==1.14.0
openpyxl==3.1.5
```

## Quick start (manuale)

Dalla radice del repository:

```bash
# 0. Creare il venv
python3 -m venv venv

# 0.5 Attivare il venv
source venv/bin/activate

# 1. Installa le dipendenze Python
pip install -r passo_base/requirements.txt

# 2. Avvia i container
docker compose up -d

# 3. Attendi che siano pronti
docker logs -f flights_neo4j       # Ctrl+C quando compare "Started"
docker logs -f flights_cassandra   # Ctrl+C quando compare "Startup complete"

# 4. Crea gli schemi
docker exec -i flights_cassandra cqlsh < Database/cassandra_schema.cql
cat Database/neo4j_schema.cypher | docker exec -i flights_neo4j cypher-shell -u neo4j -p password123

# 5. Genera i 4 dataset annidati (25/50/75/100%, scritti in Python/data/)
python Python/generate_data.py

# 6. Inserisci un dataset nei due DBMS
python Python/insert_data.py --dataset 25

# 7. Esegui il benchmark su quel dataset (31 esecuzioni × 4 query × 2 DBMS)
python Python/benchmark.py --dataset 25 --output Benchmark/benchmark_results.csv

# 8. Genera grafici e riepilogo Excel
python Python/analyze_results.py
```

`insert_data.py` e `benchmark.py` accettano `--dataset` con valori `25`, `50`, `75`, `100`. Prima di passare a un dataset diverso, i dati vanno svuotati: `insert_data.py` include una routine di pulizia, ma per repliche fedeli alla metodologia del report (container ricreato da zero per garantire uno stato cold simmetrico tra i due DBMS) conviene rigenerare i container come fa lo script di automazione qui sotto.

## Pipeline automatica completa

`Istruzioni_bash/run_experiments.sh` automatizza l'intero esperimento: per ciascuno dei quattro dataset ricrea da zero entrambi i container (elimina il problema di `MemoryPoolOutOfMemoryError` su cancellazioni massive in Neo4j e rende simmetrico il confronto sui tempi cold), reinserisce i dati, lancia il benchmark in append e infine genera grafici ed Excel.

Lo script si sposta da solo alla radice del repository all'avvio (`cd "$(dirname "$0")/.."`), quindi trova `Database/`, `Python/`, `Benchmark/` e `Immagini/` senza bisogno di essere lanciato da una cartella particolare:

```bash
bash Istruzioni_bash/run_experiments.sh
```

## Modello dati

**Neo4j**: property graph con `Reservation` come nodo reificato, perché lega tre entità (passeggero, volo, posto):

```
(:Passenger)-[:MAKES]->(:Reservation)-[:FOR_FLIGHT]->(:Flight)
(:Reservation)-[:FOR_SEAT]->(:Seat)-[:BELONGS_TO]->(:Flight)
(:Flight)-[:DEPARTS_FROM]->(:Airport)
(:Flight)-[:ARRIVES_AT]->(:Airport)
(:Flight)-[:OPERATED_BY]->(:Airline)
```

**Cassandra**: quattro tabelle progettate query first, una per ciascuna query di benchmark (`flights_by_status`, `reservations_by_passenger`, `reservations_by_airline_date`, `reservations_by_airline_airport`), più `airports` e `airlines` come tabelle di riferimento.

I dataset sono generati con Faker (seed fisso 42) e sono sottoinsiemi realmente annidati: il 100% è generato una sola volta, e il 75%, 50%, 25% sono estratti per campionamento a catena l'uno dall'altro, così una query sul 25% restituisce dati che sono davvero un pezzo del dataset completo, non una popolazione indipendente solo statisticamente simile.

## Report

L'analisi completa, con metodologia, schema ER, grafici per ogni query (prima esecuzione e media a regime con IC 95%) e discussione dei risultati, è in `PDF/Report_progetto_basi_ultimo.pdf`, compilato in LaTeX con la classe `unime.cls`.
