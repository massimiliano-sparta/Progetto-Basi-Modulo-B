# ============================================================================
# ISTRUZIONI.SH — guida passo-passo (NON lanciare con "bash istruzioni.sh")
# ----------------------------------------------------------------------------
# Questo file resta volutamente "manuale": il passo 2 richiede di guardare i
# log e premere Ctrl+C quando i database sono pronti, e un Ctrl+C dentro uno
# script bash interrompe TUTTO lo script, non solo quel comando. Copia ed
# esegui questi comandi uno alla volta dal terminale, dalla radice del
# repository (dove sta docker-compose.yml).
#
# Per un ciclo completo e automatico (reset containers, tutti e 4 i dataset,
# benchmark, grafici) usa invece: bash Istruzioni_bash/run_experiments.sh
# Per un ciclo veloce SOLO sul 25% (comodo per esercitarsi sulle query):
# bash Istruzioni_bash/istruzioni_25.sh
# ============================================================================

# 1. Avvia i container
docker compose up -d

# 2. Attendi che siano pronti (controlla i log)
docker logs -f flights_neo4j       # Ctrl+C quando vedi "Started"
docker logs -f flights_cassandra   # Ctrl+C quando vedi "Startup complete"

# 3. Crea gli schemi (percorsi corretti: cartella Database/)
docker exec -i flights_cassandra cqlsh < Database/cassandra_schema.cql
cat Database/neo4j_schema.cypher | docker exec -i flights_neo4j cypher-shell -u neo4j -p password123

# 4. Installa dipendenze Python (percorso corretto: cartella passo_base/, e -r per leggere il file)
pip install -r passo_base/requirements.txt

# 5. Genera i 4 dataset (percorso corretto: cartella Python/, e python3 non python)
python3 Python/generate_data.py

# 6. Inserisci nei DBMS — richiede il flag --dataset (25/50/75/100), non è opzionale
python3 Python/insert_data.py --dataset 25

# 7. Esegui il benchmark (31 esecuzioni × 4 query × 2 DBMS, per QUESTO dataset)
python3 Python/benchmark.py --dataset 25 --output Benchmark/benchmark_results.csv

# 8. Genera grafici e Excel (lanciare sempre dalla radice del repository)
python3 Python/analyze_results.py
