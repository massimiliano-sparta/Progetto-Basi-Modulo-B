#!/bin/bash
set -e

# Lo script va lanciato dalla radice del repository (dove sta questo
# docker-compose.yml). FIX rispetto alla versione precedente: gli
# schemi e gli script Python sono stati riorganizzati in Database/ e
# Python/, ma lo script li referenziava ancora per nome nudo e
# falliva subito su "file not found". I percorsi qui sotto sono ora
# relativi alla radice del repository.
cd "$(dirname "$0")/.."

# FIX: la pulizia di Neo4j tramite "MATCH (n) DETACH DELETE n" (anche a
# lotti, anche con la memoria transazionale sbloccata) diventa inaffidabile
# man mano che il grafo cresce (funzionava su ~300k nodi, falliva su
# ~580k). Invece di continuare a inseguire i parametri di memoria della
# JVM, si aggira il problema alla radice: si ricrea il container Neo4j
# da zero prima di ogni dataset. Un container appena avviato e' vuoto
# all'istante, zero query di delete, zero rischio di OOM.
reset_neo4j() {
    echo "  Reset completo container Neo4j..."
    docker stop flights_neo4j >/dev/null 2>&1 || true
    docker rm -f flights_neo4j >/dev/null 2>&1 || true

    VOL=$(docker volume ls -q --filter "name=neo4j_data")
    if [ -n "$VOL" ]; then
        docker volume rm $VOL >/dev/null 2>&1 || true
    fi

    docker compose up -d neo4j >/dev/null

    echo -n "  Attendo che Neo4j sia pronto"
    tries=0
    until [ "$(docker inspect -f '{{.State.Health.Status}}' flights_neo4j 2>/dev/null)" = "healthy" ]; do
        echo -n "."
        sleep 2
        tries=$((tries + 1))
        if [ "$tries" -gt 60 ]; then
            echo ""
            echo "  ERRORE: Neo4j non è diventato 'healthy' entro 2 minuti."
            echo "  Controlla i log con: docker logs flights_neo4j"
            exit 1
        fi
    done
    echo " ok"

    echo "  Ricreo constraint/indici Neo4j..."
    cat Database/neo4j_schema.cypher | docker exec -i flights_neo4j cypher-shell -u neo4j -p password123 >/dev/null
}

# Speculare a reset_neo4j(): elimina l'asimmetria tra i due container.
# Prima Cassandra veniva solo svuotata con TRUNCATE (non aveva mostrato
# gli stessi problemi di memoria di Neo4j), restando lo stesso processo
# per tutta la durata degli esperimenti — questo la avvantaggiava sui
# tempi di "prima esecuzione", che beneficiavano di una JVM già calda.
# Ricreando anche questo container, entrambi i DBMS ripartono da zero
# a ogni dataset, rendendo il confronto sui tempi cold davvero simmetrico.
reset_cassandra() {
    echo "  Reset completo container Cassandra..."
    docker stop flights_cassandra >/dev/null 2>&1 || true
    docker rm -f flights_cassandra >/dev/null 2>&1 || true

    VOL=$(docker volume ls -q --filter "name=cassandra_data")
    if [ -n "$VOL" ]; then
        docker volume rm $VOL >/dev/null 2>&1 || true
    fi

    docker compose up -d cassandra >/dev/null

    echo -n "  Attendo che Cassandra sia pronta"
    tries=0
    # Cassandra in genere impiega piu' tempo di Neo4j a diventare pronta
    # (bootstrap, gossip): timeout piu' largo, 3 minuti invece di 2.
    until [ "$(docker inspect -f '{{.State.Health.Status}}' flights_cassandra 2>/dev/null)" = "healthy" ]; do
        echo -n "."
        sleep 2
        tries=$((tries + 1))
        if [ "$tries" -gt 90 ]; then
            echo ""
            echo "  ERRORE: Cassandra non è diventata 'healthy' entro 3 minuti."
            echo "  Controlla i log con: docker logs flights_cassandra"
            exit 1
        fi
    done
    echo " ok"

    echo "  Ricreo keyspace/tabelle Cassandra..."
    cat Database/cassandra_schema.cql | docker exec -i flights_cassandra cqlsh >/dev/null
}

mkdir -p Benchmark Immagini
rm -f Benchmark/benchmark_results.csv

for ds in 25 50 75 100; do
    echo ""
    echo "=========================================="
    echo " DATASET ${ds}%"
    echo "=========================================="
    reset_neo4j
    reset_cassandra
    python Python/insert_data.py --dataset $ds
    python Python/benchmark.py --dataset $ds --append --output Benchmark/benchmark_results.csv
done

echo ""
echo "=========================================="
echo " Generazione grafici e Excel..."
# FIX: analyze_results.py legge/scrive con percorsi relativi alla cwd
# ("benchmark_results.csv", "qN_first.png", "results.xlsx"), invariato
# rispetto all'originale. Lo lanciamo quindi da dentro Benchmark/, dove
# ora vive il csv, cosi' anche results.xlsx finisce li' insieme ad
# esso; i soli PNG generati vengono poi spostati in Immagini/, per
# rispecchiare la struttura di cartelle gia' presente nel repository.
( cd Benchmark && python ../Python/analyze_results.py )
mv Benchmark/q*_first.png Benchmark/q*_avg.png Immagini/
echo "Done!"
