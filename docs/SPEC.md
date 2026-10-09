# Specifica — donazioni settimanali Italia

## Ambito

Job Python eseguito ogni lunedì alle 00:00 UTC. Italia soltanto
(`6813b6d446e731854c7ac7a2`), top 10 per percentuale selezionata dai primi 50 player per importo. Nessun database,
server HTTP, aggiornamento continuo o sito web. Template HTML/CSS locale per generare il PNG.

## Periodo e calcolo

- Ultima settimana conclusa: `[lunedì precedente 00:00 UTC, lunedì corrente 00:00 UTC)`.
  Il riferimento è l'istante di avvio; l'ora legale non modifica i confini.
- Leggere `transaction.getPaginatedTransactions` con Italia, `donation`, `limit: 100`.
  Risposta verificata: `items`, `nextCursor`; donatore `buyerId`, destinatario `sellerCountryId`.
- Paginare dal più recente, saltando le donazioni della settimana corrente.
  Deduplicare per `_id`, verificare ordine decrescente e filtrare destinatario e intervallo.
  Fermarsi quando una pagina contiene una donazione precedente all'inizio del periodo.
- Sommare con Decimal per player, indipendentemente dalla cittadinanza.
  Ordinare per importo decrescente, parità per ID crescente; selezionare i primi 50.
- Recuperare i profili con un solo batch GET tRPC `user.getUserById`, fino a 50 procedure.
- `P = stats.wealth.total - stats.wealth.companies`; `percentuale = 100 * donazioni / P`.
  Escludere i candidati con profilo/wealth mancanti o `P <= 0`.
- Ordinare i candidati validi per rapporto decrescente, poi importo decrescente e ID crescente.
  Selezionare al massimo 10 player e assegnare le posizioni finali da 1.
  Arrotondare soltanto dopo la selezione a tre decimali con ROUND_HALF_UP.
  La top 10 è limitata ai 50 candidati iniziali; può contenere meno di 10 righe.
- P è patrimonio osservato durante l'esecuzione, non guadagno settimanale o sola liquidità.
  Una riesecuzione può modificare P; non esiste recupero storico del wealth in questa versione.

## Esecuzione e output

Chiave da `WARERA_API_KEY`, header `X-API-Key`. Comando `python -m warera_rankings`,
output `data/italy-YYYY-MM-DD.json` o directory indicata con `--output-dir`.
JSON scritto atomicamente solo dopo il calcolo; errori non sostituiscono il file precedente.
Timestamp UTC, totale donato, numero di donazioni/donatori, `candidate_count` (massimo 50),
copertura e righe della top 10 finale. Totali e conteggi delle donazioni riguardano tutti i donatori.
Ogni riga contiene posizione, ID/nome, importo, numero donazioni, wealth totale,
valore aziende, P e percentuale. Include `avatar_url` da `avatarUrl`
e `level` da `leveling.level`, null se assenti. Sono letti nello stesso batch dei profili.
Importi serializzati come stringhe decimali.
Nessuna chiave o profilo integrale nel risultato o negli errori.

## Grafica

Extra `image`: Jinja2 e Playwright con Chromium headless installato per l'utente del job.
`python -m warera_rankings --image` aggiunge il PNG all'esportazione JSON.
`python -m warera_rankings.image <file.json> [--output <file.png>]` rigenera il PNG
dal JSON esistente senza chiave o chiamate alle API WarEra. Schema e calcolo invariati.

Template incluso nel pacchetto: `warera_rankings/templates/weekly.html`.
Larghezza 1200 px e altezza adattata al contenuto. Righe nello stesso ordine del JSON:
posizione, nome, avatar, livello, donazioni, patrimonio escluso aziende e percentuale
a tre decimali, con separatori italiani. Titolo «Classifica settimanale donatori»
e periodo senza etichetta UTC, seguiti direttamente dalla tabella. Nessun riepilogo
di totali o conteggi e nessuna nota in calce. Bandierina e «WARERA / ITALIA» sulla stessa riga.
Medaglie SVG oro, argento e bronzo per le prime tre posizioni; numeri per le successive.
Copertura non verificata segnalata come risultato provvisorio. Lista vuota gestita.

Nomi sottoposti a escaping HTML. Avatar scaricati in parallelo con HTTPX, timeout 8 secondi,
limite 2 MB ciascuno, solo PNG/JPEG/WebP/GIF; errori o contenuti non decodificabili
usano l'iniziale del nome. Immagini incorporate nel template, nessuna rete dal browser
o font esterno. Il download degli avatar è aggiuntivo al costo HTTP delle API WarEra.
Attendere decodifica immagini e font prima dello screenshot.

Scrittura PNG atomica; un errore non sostituisce il PNG precedente. JSON e PNG sono
esportazioni separate: un errore grafico lascia il JSON nuovo disponibile ed esce con
codice 1. Il PNG precedente può quindi riferirsi a una precedente esecuzione.

## Accesso API

Timeout HTTP 20 secondi, fino a 2 retry aggiuntivi per rete/429/5xx; rispettare header quota.
Budget 240 secondi e massimo 200 pagine. Errori, cursori ciclici e ordine invalido interrompono
il job con exit code 1. Costo HTTP: pagine lette + 1 batch, salvo retry; nessun batch senza donatori.

## Copertura e automazione

`week_boundary_reached`: oltrepassato l'inizio del periodo nello storico ordinato restituito
dall'API; presuppone la continuità dei dati del provider. Se la paginazione termina prima,
`history_unverified`: esportazione esplicitamente provvisoria, senza garanzia di completezza.

Timer systemd: lunedì 00:00 UTC, con recupero di un'attivazione persa.
Il servizio usa `--image` e genera JSON e PNG. Nessun backfill di settimane più vecchie,
nessuna distribuzione/pubblicazione automatica oltre ai file locali.
Pubblicazione su r/WarEraITA da integrare dopo approvazione dell'accesso API Reddit.
Una sola attivazione per chiave/output.

## Prova reale — 9 ottobre 2026

Periodo 28 settembre–5 ottobre UTC: 587 donazioni, 170 donatori, totale 13963.859,
50 profili validi. Scansione oltre l'inizio del periodo; 11 pagine e 1 batch (12 HTTP).
Quota autenticata osservata: 500 richieste ogni 60 secondi. Questa esecuzione tardiva
utilizza il wealth del 9 ottobre; non ricostruisce il patrimonio del 5 ottobre.

## Verifica automatica

Test su confini UTC, intervallo esclusivo, deduplicazione, selezione dei 50 candidati,
top 10 per rapporto, esclusioni e parità, ordinamento prima dell'arrotondamento, precisione,
rapporti non calcolabili, parser reale, batch parziale, retry/quota, job integrato
con rete simulata ed esportazione atomica. Ruff e pytest eseguiti anche in CI.
Test grafici su escaping, formattazione, risultati vuoti/provvisori, fallback avatar,
limiti download, PNG generato da Chromium, nomi lunghi e conservazione del PNG su errore.

Riferimenti: [API WarEra](https://api2.warera.io/docs/),
[client di riferimento](https://github.com/WarEraProjects/api-client-py).
