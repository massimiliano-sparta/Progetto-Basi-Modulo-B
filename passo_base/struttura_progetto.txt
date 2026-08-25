## Struttura del repository

```
.
├── docker-compose.yml              # Neo4j 5.24 + Cassandra 4.1, risorse comparabili
├── Database/
│   ├── neo4j_schema.cypher         # Constraint di unicità e indici
│   └── cassandra_schema.cql        # Keyspace e 4 tabelle denormalizzate
├── Python/
│   ├── generate_data.py            # Generazione dataset con Faker (seed=42)
│   ├── insert_data.py              # Inserimento batch in Neo4j e Cassandra
│   ├── benchmark.py                # 31 esecuzioni per query, cold + warm
│   └── analyze_results.py          # Grafici e riepilogo Excel dai risultati
├── Istruzioni_bash/
│   ├── run_experiments.sh          # Pipeline completa: reset container → insert → benchmark → grafici
│   ├── istruzioni.sh               # Sequenza manuale dei comandi, passo per passo
│   └── comando_da_sapere.txt
├── Benchmark/
│   ├── benchmark_results.csv       # Output grezzo di benchmark.py
│   └── results.xlsx
├── Immagini/                       # Istogrammi generati da analyze_results.py
├── PDF/
│   ├── Report_progetto_basi_ultimo.pdf
│   ├── basi_di_dati_nosql-tracce_progetti_2026_published.pdf
│   └── guida_progetti_basi_di_dati-nosql_2026.pdf
└── passo_base/
    └── requirements.txt             # Dipendenze Python
```
