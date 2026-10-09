# WarEra Donators

Job Python che seleziona i primi 50 donatori all'Italia per importo nella settimana UTC
appena conclusa e pubblica i primi 10 per percentuale sul patrimonio escluso aziende.
Esporta un JSON con foto profilo, livello, importi, patrimonio e percentuale a tre decimali.
Nessun database o processo HTTP persistente.

La top 10 riguarda esclusivamente i 50 candidati: il rapporto viene ordinato prima
dell'arrotondamento. Parità: importo donato decrescente, poi ID crescente.
Candidati con rapporto non calcolabile esclusi; il risultato può contenere meno di 10 player.

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

## Esecuzione automatica

I modelli in `deploy/` eseguono il job ogni lunedì alle **00:00 UTC** con systemd.
Installare il progetto in `/opt/warera-rankings`, creare l'utente `warera` e assegnargli
accesso al progetto e alla directory dati. Installazione runtime: `python -m pip install -e .`.

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
pytest
ruff check .
ruff format --check .
```

CI su push e pull request. I test non accedono alla rete né richiedono una chiave.
Schema delle donazioni e batch dei profili verificati con API reale il 9 ottobre 2026.
La [specifica](docs/SPEC.md) descrive formule e limiti.
