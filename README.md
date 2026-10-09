# WarEra Donators

Job Python che seleziona i primi 50 donatori all'Italia per importo nella settimana UTC
appena conclusa e pubblica i primi 10 per percentuale sul patrimonio escluso aziende.
Esporta un JSON con foto profilo, livello, importi, patrimonio e percentuale a tre decimali.
Può generare anche un PNG della classifica, pronto per un post su r/WarEraITA.
Nessun database o processo HTTP persistente.

La top 10 riguarda esclusivamente i 50 candidati: il rapporto viene ordinato prima
dell'arrotondamento. Parità: importo donato decrescente, poi ID crescente.
Candidati con rapporto non calcolabile esclusi; il risultato può contenere meno di 10 player.

## Controllo possibili quit

Configurazione in `config.toml`, selezionabile con `--config`. Il controllo è attivo:
impostare `[quit_detection] enabled = false` per disabilitarlo.
I sospetti vengono esclusi prima della top 10, che viene completata con i candidati
rimanenti fra i 50 iniziali. Il JSON contiene `quit_exclusions` con player e segnali;
con controllo disattivato questo campo e gli snapshot non vengono generati.
Totali delle donazioni invariati, inclusi gli esclusi.

Regola: donazioni settimanali maggiori del patrimonio escluso aziende,
almeno due segnali patrimoniali e almeno `minimum_signals` segnali complessivi.
Soglie iniziali modificabili nel file:

| Segnale | Soglia |
| --- | --- |
| Poco lavoro | Al massimo 5 lavori nella settimana |
| Poche missioni | Al massimo 5 missioni nella settimana |
| Poco denaro | Al massimo 10 |
| Poco equipaggiamento | Armi + equipaggiamento al massimo 100 |
| Basso valore delle aziende | Al massimo 1.000, esclusi dalla somma di armi/equip |
| Donazioni concentrate | Almeno l’80% dell’importo in 10 minuti, almeno 2 donazioni |
| Donazioni superiori al patrimonio netto | Rapporto strettamente maggiore del 100% |

I segnali patrimoniali sono denaro, equipaggiamento e valore aziende: quest’ultimo
è una soglia sul valore, non sul numero di aziende. Minimo iniziale: 4 segnali.
È un’euristica di possibile liquidazione, non una conferma dell’abbandono.

I conteggi di lavori/missioni sono cumulativi nelle API: si confrontano gli snapshot
`data/activity-YYYY-MM-DD.json` dei due lunedì, acquisiti entro un’ora dalle 00:00 UTC.
Sono salvati per i 50 candidati con i dati disponibili, senza altre chiamate API.
La prima rilevazione viene conservata anche nelle riesecuzioni della stessa settimana.
Se manca una rilevazione valida, si cercano lavoro e missioni non aggiornati da oltre
3 giorni rispetto alla chiusura della settimana. Date o valori mancanti sono sconosciuti,
mai zero; contatori diminuiti non producono un delta. Una rilevazione tardiva non
ricostruisce il patrimonio o l’attività storica. I file attività restano locali e ignorati da Git.

## Avvio

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Inserire la chiave in `.env`, quindi:

```bash
set -a
source .env
set +a
python -m warera_rankings
```

Il comando calcola sempre l'ultima settimana conclusa, anche se eseguito dopo lunedì.
Output: `data/italy-YYYY-MM-DD.json`, con la data di inizio settimana.
La directory è modificabile con `--output-dir`. File `.env` e risultati sono ignorati da Git.
Una nuova esecuzione sostituisce atomicamente il file della stessa settimana.

Il wealth è quello osservato durante l'esecuzione, non un patrimonio storico recuperato
alla chiusura. La percentuale può superare il 100% e non rappresenta una quota del guadagno settimanale.
`coverage: history_unverified` identifica un risultato provvisorio.

## Immagine della classifica

Installare le dipendenze opzionali e Chromium:

```bash
python -m pip install -e '.[image]'
python -m playwright install --only-shell chromium
```

Su un server Linux che richiede librerie di sistema, usare
`python -m playwright install --with-deps --only-shell chromium`.
Installare Chromium con lo stesso utente che eseguirà il job, anche per systemd:
il browser viene salvato nella cache dell'utente.

Calcolo ed esportazione JSON + PNG:

```bash
python -m warera_rankings --image
```

Rigenerare soltanto l'immagine, senza chiave né chiamate alle API WarEra:

```bash
python -m warera_rankings.image data/italy-2026-09-28.json
```

Il PNG ha lo stesso nome del JSON e larghezza 1200 px; `--output` permette di scegliere
un altro percorso. Il template modificabile è `warera_rankings/templates/weekly.html`.
Mostra l'ordine del JSON, avatar, livello, donazioni, patrimonio escluso aziende e rapporto
a tre decimali. Titolo «Classifica settimanale donatori», periodo e tabella, senza riepilogo.
Bandierina e «WARERA / ITALIA» sono sulla stessa riga.
Le prime tre posizioni mostrano medaglie oro, argento e bronzo.
I membri Confindustria hanno il nome oro come «TOP 10», gli altri bianco. In fondo:
legenda dei colori e «Patrimonio al netto del valore delle aziende».
La lista viene aggiornata a ogni rendering dalla
[API pubblica Confindustria](https://confindustria-rust.vercel.app/players.json).
Formato: array di oggetti con `id` e `name`; il confronto usa solo l'ID.
Una richiesta aggiuntiva, senza chiave, con timeout 8 secondi. Se la risposta è invalida
o il servizio non è raggiungibile, il PNG viene generato con tutti i nomi bianchi.
Nessuna lista locale sostitutiva. JSON della classifica e ordine restano invariati.
Avatar non disponibili o invalidi sostituiti dall'iniziale del nome; nessun font esterno.
Le immagini profilo vengono scaricate a ogni rendering: timeout 8 secondi e massimo 2 MB
per avatar. Queste richieste sono aggiuntive rispetto alle chiamate alle API WarEra.

JSON e PNG vengono sostituiti atomicamente, ciascuno separatamente. Se il rendering fallisce,
il comando termina con errore, ma il JSON appena calcolato e l'eventuale PNG precedente
restano disponibili. Rigenerare il PNG prima di utilizzarlo per la pubblicazione.
Il JSON e il calcolo non cambiano. La pubblicazione Reddit sarà collegata dopo
l'approvazione dell'accesso API; questa versione genera soltanto i file locali.

## Esecuzione automatica

I modelli in `deploy/` eseguono il job ogni lunedì alle **00:00 UTC** con systemd.
Installare il progetto in `/opt/warera-rankings`, creare l'utente `warera` e assegnargli
accesso al progetto e alla directory dati. Installazione runtime:
`python -m pip install -e '.[image]'`, poi installare Chromium come indicato sopra.
Il servizio genera JSON e PNG durante la stessa esecuzione.
Conservare `config.toml` nella directory del progetto; il servizio lo legge a ogni avvio.

Copiare `deploy/warera-rankings.service` e `deploy/warera-rankings.timer` in
`/etc/systemd/system/`, poi:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now warera-rankings.timer
```

Il timer è un modello, non è stato installato sul server. `Persistent=true` recupera
un'attivazione persa, ma calcola solo l'ultima settimana conclusa: non effettua backfill.
Conservare i JSON su disco persistente. Non è necessario lasciare il programma acceso.

## Test

```bash
python -m pip install -e '.[dev,image]'
python -m playwright install --only-shell chromium
pytest
ruff check .
ruff format --check .
```

CI su push e pull request, inclusi test di rendering con Chromium.
I test non accedono alla rete né richiedono una chiave.
Schema delle donazioni e batch dei profili verificati con API reale il 9 ottobre 2026.
La [specifica](docs/SPEC.md) descrive formule e limiti.
