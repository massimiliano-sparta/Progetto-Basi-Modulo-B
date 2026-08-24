# 1. Avvia i container
docker-compose up -d

# 2. Attendi che siano pronti (controlla i log)
docker logs -f flights_neo4j   # Ctrl+C quando vedi "Started"
docker logs -f flights_cassandra # Ctrl+C quando vedi "Startup complete"

# 3. Crea gli schemi
docker exec -i flights_cassandra cqlsh < cassandra_schema.cql
cat neo4j_schema.cypher | docker exec -i flights_neo4j cypher-shell -u neo4j -p password123

# 4. Installa dipendenze Python
pip install -r requirements.txt

# 5. Genera i 4 dataset
python generate_data.py

# 6. Inserisci nei DBMS (può richiedere tempo per il 100%)
python insert_data.py

# 7. Esegui il benchmark (31 esecuzioni × 4 query × 2 DBMS × 4 dataset)
python benchmark.py

# 8. Genera grafici e Excel
python analyze_results.py
