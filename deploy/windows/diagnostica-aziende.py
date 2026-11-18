import os
import sys
from pathlib import Path

from dotenv import dotenv_values
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[2] / "backend"
env = next((dotenv_values(ROOT / n) for n in (".env", ".env.txt") if (ROOT / n).is_file()), {})
url, dbn, admin = env.get("MONGO_URL"), env.get("DB_NAME"), (env.get("ADMIN_EMAIL") or "").lower()
if not url or not dbn:
    sys.exit(f"MONGO_URL o DB_NAME mancanti in {ROOT / '.env'}")
cli = MongoClient(url, serverSelectionTimeoutMS=5000)
db = cli[dbn]
print(f"File configurazione: {ROOT / '.env'}")
print(f"Database in uso: {dbn}")
print(f"Altri database sul server: {', '.join(n for n in cli.list_database_names() if n not in ('admin', 'local', 'config', dbn)) or 'nessuno'}")
for n in cli.list_database_names():
    if n not in ("admin", "local", "config") and "companies" in cli[n].list_collection_names():
        print(f"  - {n}: {cli[n].companies.count_documents({})} aziende")
print(f"\nAziende nel database in uso: {db.companies.count_documents({})}")
for c in db.companies.find({}, {"_id": 0, "denominazione": 1, "partita_iva": 1}).sort("denominazione", 1):
    print(f"  - {c.get('denominazione')} ({c.get('partita_iva', '')})")
print("\nUtenti:")
for u in db.users.find({}, {"_id": 0, "email": 1, "role": 1, "status": 1, "company_ids": 1}):
    print(f"  - {u.get('email')}: ruolo={u.get('role')} stato={u.get('status')} aziende assegnate={len(u.get('company_ids') or [])}")
if "--ripara-admin" in sys.argv and admin:
    r = db.users.update_one({"email": admin}, {"$set": {"role": "admin", "status": "approved"}})
    print(f"\nRuolo amministratore ripristinato per {admin}" if r.matched_count else f"\nUtente {admin} non trovato")
