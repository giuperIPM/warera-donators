# Specifica — classifica settimanale Italia

## Ambito

Servizio Python 3.12 + FastAPI su server persistente, singolo processo.
Solo Italia (`6813b6d446e731854c7ac7a2`), settimana corrente e primi 50 player
per totale donato. Nessun parametro per altri Stati, periodi o dimensioni.
Qualsiasi cittadinanza è ammessa: conta lo Stato destinatario.

## Calcolo

- Settimana di calendario: lunedì 00:00–lunedì successivo, `Europe/Rome`.
  Timestamp in UTC e intervallo `[inizio settimana, avvio aggiornamento)`.
- `transaction.getPaginatedTransactions`: Italia, tipo `donation`, pagine da 100.
  Cursori sequenziali; deduplicazione per transazione; verifica dell'ordine
  decrescente osservato. Stop dopo una pagina contenente record precedenti alla settimana.
- Somma decimale per player; ordine per importo decrescente, parità per ID crescente.
- Un batch GET tRPC di `user.getUserById` per i primi 50, senza richieste alle aziende.
- `patrimonio escluso aziende = stats.wealth.total − stats.wealth.companies`.
- `percentuale = 100 × donazioni / patrimonio escluso aziende`, solo con patrimonio positivo.
  Patrimonio mancante/non positivo: percentuale `null` e motivo. Nessun valore inventato.
- La percentuale è una colonna dei top 50 per importo, non una classifica globale per rapporto.
  Il denominatore è patrimonio attuale, non guadagno settimanale né sola liquidità.
  Importi e percentuali serializzati come stringhe decimali.

## Aggiornamento automatico

Un task avviato con il server calcola subito la classifica, poi attende 15 minuti
tra aggiornamenti. SQLite salva una fotografia per settimana, aggiornata atomicamente;
le settimane precedenti rimangono archiviate. Non è ancora un archivio delle singole donazioni
né garantisce una fotografia definitiva alla chiusura della settimana.
Un aggiornamento fallito mantiene il risultato precedente.

Chiave: `WARERA_API_KEY`. Archivio: `WARERA_DATABASE`, default `data/rankings.sqlite3`.
Senza chiave gli aggiornamenti sono disabilitati; eventuali fotografie restano consultabili.
File `.env` caricabile da systemd o dalla shell, non automaticamente dall'applicazione.
Eseguire una sola istanza e un solo worker Uvicorn per database/API key.

Client HTTP asincrono con timeout 20 secondi, massimo 2 retry aggiuntivi per
errori di rete, 429 e 5xx. Attesa secondo gli header di quota. Budget 240 secondi
e massimo 200 pagine per aggiornamento: superamento o paginazione invalida non salva risultati parziali.
Il numero HTTP è pagine lette + 1 batch profili, esclusi retry; senza donatori nessun batch.

## HTTP

- `GET /health`: processo disponibile, aggiornamenti abilitati, ultimo tentativo/errore.
  Non è una garanzia di completezza dei dati.
- `GET /api/rankings/weekly`: ultima fotografia, stato di aggiornamento e flag `stale`.
  `stale` se i dati hanno più di 30 minuti o appartengono a un'altra settimana.
  Prima fotografia non disponibile: 503 con `Retry-After: 30`.
- Nessun endpoint pubblico di refresh; le letture non interrogano WarEra.
  Risposte `no-store`, evitando che una cache nasconda lo stato aggiornato.
- Ogni riga contiene posizione, ID/nome, somma e numero donazioni, wealth totale,
  aziende, patrimonio escluso aziende, percentuale, stato del profilo.
- Un errore di una singola procedura batch lascia disponibili gli importi e marca
  il profilo come non disponibile. Fallimento dell'intera richiesta conserva la fotografia precedente.

## Completezza e verifiche aperte

`coverage: week_boundary_reached` indica che la scansione ha oltrepassato l'inizio
della settimana; presuppone la continuità dello storico restituito dal provider.
Se lo storico termina prima, `coverage: history_unverified`: risultato provvisorio,
senza dichiarazione di completezza. Interruzioni, ordine crescente o cicli di cursori falliscono esplicitamente.

Le donazioni richiedono una chiave. Prima dell'uso reale verificare envelope `items/nextCursor`,
campi donatore/destinatario e retention: il parser supporta `buyerId/sellerCountryId`
e `userId/countryId`, segnalando i dati ambigui. Quota autenticata e accessibilità dal server
restano da misurare. Profili wealth e batch GET sono già stati provati senza chiave.
Nessun token o profilo integrale è esposto nelle risposte o nei messaggi di errore.

## Validazione

Test automatici: aggregazione/deduplicazione, confini e ora legale, top 50 e parità,
rapporti non calcolabili, parser e batch con errori, retry/quota, persistenza,
conservazione del risultato in caso di errore, lettura HTTP e ciclo automatico.
Lint con Ruff. CI esegue gli stessi controlli su push e pull request.

Fonti: [API WarEra](https://api2.warera.io/docs/),
[client di riferimento](https://github.com/WarEraProjects/api-client-py),
[pywarera](https://github.com/Marerjh/pywarera).
