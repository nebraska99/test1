# TELAIO STRATEGIE (V1)

Living dashboard locale per:
- caricare CSV TradingView
- pulire/importare automaticamente i dati
- aggiornare storico persistente
- calcolare segnali Momentum Multi Asset
- vedere ranking e semaforo in dashboard web

---

## 1) Prerequisiti (semplici)

- Python 3.11+ installato
- Terminale (Windows PowerShell / Mac Terminal)

---

## 2) Installazione (copia/incolla)

Apri terminale nella cartella del progetto e lancia:

```bash
python -m venv .venv
source .venv/bin/activate   # su Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3) Avvio app

```bash
uvicorn app.main:app --reload
```

Poi apri nel browser:

- http://127.0.0.1:8000

---

## 4) Come caricare i CSV TradingView

1. Apri la home della dashboard.
2. Nel box **Upload CSV TradingView**, clicca su **Scegli file**.
3. Seleziona uno o più CSV esportati da TradingView.
4. Clicca **Carica file**.

Il sistema:
- salva sempre il raw originale in `data/raw_uploads/`
- importa/normalizza in SQLite
- aggiorna lo storico senza cancellare passato
- genera snapshot segnali momentum

---

## 5) Dove vedere i segnali

Nella stessa home:
- box **Momentum Multi Asset** (stato ultimo run)
- tabella **Ranking strumenti (ultimo snapshot)**
  - Mom 3M, 6M, 12M, 12-1M
  - filtro absolute momentum (>0 su 12M)
  - semaforo finale (GREEN / YELLOW / RED)

---

## 6) Dati persistenti (dove sono)

- Database: `data/telaio_strategie.db`
- Raw uploads: `data/raw_uploads/`
- Placeholder snapshot files: `data/signal_snapshots/`
- Config placeholder: `data/config/`
- Portfolio placeholder: `data/portfolios/`

---

## 7) Note importanti

- V1 ottimizzata per robustezza e semplicità.
- Nessuna pulizia manuale CSV richiesta.
- Se ci sono anomalie, vengono registrate in `import_logs` nel database.
- Moduli futuri già predisposti in `app/modules/`.
