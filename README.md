# WarEra Rankings

Classifica della settimana corrente delle donazioni all'Italia: primi 50 player
per importo e percentuale rispetto al patrimonio escluso aziende.
Python, FastAPI, SQLite; esecuzione su server persistente.

## Avvio

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Inserire `WARERA_API_KEY` in `.env`, poi avviare:

```bash
set -a
source .env
set +a
uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Il server aggiorna subito la classifica e poi attende 15 minuti tra aggiornamenti.
Le richieste HTTP leggono SQLite senza chiamare WarEra.

- Classifica: <http://127.0.0.1:8000/api/rankings/weekly>
- Stato: <http://127.0.0.1:8000/health>
- Contratto HTTP: <http://127.0.0.1:8000/docs>

Prima del primo risultato l'endpoint restituisce 503. Senza chiave, gli aggiornamenti
sono disabilitati. Dopo un errore resta disponibile la fotografia precedente con
timestamp, errore e indicazione di obsolescenza. `history_unverified` indica una copertura
settimanale non accertata: non trattare quel risultato come classifica completa.

## Test

```bash
pytest
ruff check .
ruff format --check .
```

I test usano risposte simulate e database temporanei, senza chiave né chiamate reali.
La prova integrata autenticata delle donazioni è ancora da eseguire.
La CI esegue test e lint su push e pull request.

## Server

Installare il progetto in `/opt/warera-rankings`, creare l'utente `warera` e assegnargli
permessi sul progetto e sulla directory dati. Per l'ambiente di produzione bastano
le dipendenze runtime: `python -m pip install -e .`.

Il file [deploy/warera-rankings.service](deploy/warera-rankings.service) è un modello
systemd con riavvio automatico e caricamento di `.env`. Copiarlo in `/etc/systemd/system/`,
quindi eseguire `systemctl daemon-reload` e `systemctl enable --now warera-rankings`.
Il modello non è ancora stato installato su un server. Esporre il servizio tramite reverse proxy HTTPS.

Eseguire un solo worker e una sola istanza per evitare aggiornamenti duplicati.
Conservare `data/` su disco persistente e includerla nei backup.
SQLite salva fotografie delle classifiche, non tutte le transazioni originali.

La [specifica](docs/SPEC.md) documenta formule, limiti e verifiche ancora aperte.
