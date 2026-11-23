"""Avviso di aggiornamento agli utenti collegati. Uso: avviso-aggiornamento.py inizio [secondi] | fine"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")
db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=10000)[os.environ["DB_NAME"]]

if sys.argv[1:2] == ["fine"]:
    db.sistema_avvisi.delete_many({"tipo": "aggiornamento"})
    print("Avviso di aggiornamento rimosso.")
else:
    sec = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    now = datetime.now(timezone.utc)
    db.sistema_avvisi.delete_many({"tipo": "aggiornamento"})
    db.sistema_avvisi.insert_one({"tipo": "aggiornamento", "creato_il": now.isoformat(), "spegnimento_at": (now + timedelta(seconds=sec)).isoformat(),
                                  "messaggio": "Il sistema si sta aggiornando: tra pochi secondi verrà spento e riavviato. Salva subito il lavoro in corso; potrai rientrare tra qualche minuto."})
    print(f"Avviso inviato agli utenti collegati: aggiornamento tra {sec} secondi.")
