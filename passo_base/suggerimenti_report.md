## 6. Suggerimenti per il report (15-20 pagine)

| Sezione | Contenuto | Punti guida |
|---|---|---|
| **Problema** | Descrizione del dominio Flight Reservation, entità e relazioni, obiettivo del confronto | 2 |
| **DBMS** | Neo4j (property graph, Cypher, ottimo per join/traversali) vs Cassandra (wide-column, query-first design, denormalizzazione) | 2 |
| **Progettazione** | Schema ER originale → adattamento a grafo Neo4j (nodi + relazioni) → adattamento a tabelle Cassandra (query-driven, annidamento). Mostra lo schema logico di entrambi | 6 |
| **Implementazione** | Snippet di codice per inserimento (UNWIND Neo4j, execute_concurrent Cassandra) e le 4 query con commento sulla complessità | 6 |
| **Esperimenti** | Tabella tempi (first + avg ± IC 95%), 8 istogrammi (4 query × 2 tipologie), discussione su cold vs warm cache | 6 |
| **Conclusioni** | Quando vince Neo4j (query complesse, traversali multi-hop) e quando Cassandra (lookup puntuali, scalabilità lineare su partizioni). Trade-off flessibilità vs prestazioni | 3 |

### Note importanti per il report
- **Q1 (1 entità)**: Cassandra è molto veloce (partizione su `status`). Neo4j usa l'indice su `status`; potrebbe essere leggermente più lento per l'overhead del grafo.
- **Q2-Q3 (2-5 entità)**: Cassandra mantiene buone prestazioni grazie alla denormalizzazione, ma a costo di storage e rigidezza. Neo4j inizia a mostrare il vantaggio dei traversali nativi.
- **Q4 (aggregazione)**: Cassandra può aggregare su singola partizione (grazie alla modifica dello schema con `departure_date` come clustering), ma non su partizioni multiple. Neo4j esegue l'aggregazione in una sola query Cypher anche attraverso molte relazioni. Questo è il punto chiave di discussione.
