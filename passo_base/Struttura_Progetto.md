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
