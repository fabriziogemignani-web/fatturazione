import contextvars
import functools
import logging

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.errors import PyMongoError

log = logging.getLogger("integrita")
_SESSION: contextvars.ContextVar = contextvars.ContextVar("tx_session", default=None)
_STATE = {"client": None, "attive": False}
_METODI = {"find", "find_one", "insert_one", "insert_many", "update_one", "update_many", "replace_one", "delete_one", "delete_many",
           "find_one_and_update", "find_one_and_delete", "find_one_and_replace", "count_documents", "aggregate", "distinct", "bulk_write"}


class _Coll:
    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        v = getattr(self._real, name)
        if isinstance(v, AsyncIOMotorCollection):
            return _Coll(v)
        if name not in _METODI:
            return v

        def call(*a, **k):
            s = _SESSION.get()
            if s is not None and "session" not in k:
                k["session"] = s
            return v(*a, **k)
        return call


class TxDB:
    """Database che usa in automatico la transazione aperta da @atomico."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        v = getattr(self._real, name)
        return _Coll(v) if isinstance(v, AsyncIOMotorCollection) else v

    def __getitem__(self, name):
        return _Coll(self._real[name])


async def rileva(client):
    _STATE["client"] = client
    try:
        hello = await client.admin.command("hello")
        _STATE["attive"] = bool(hello.get("setName") or hello.get("msg") == "isdbgrid")
    except PyMongoError:
        _STATE["attive"] = False
    log.info("Transazioni MongoDB %s", "attive" if _STATE["attive"] else "non disponibili (database senza replica set)")
    return _STATE["attive"]


def transazioni_attive() -> bool:
    return _STATE["attive"]


def atomico(fn):
    @functools.wraps(fn)
    async def w(*a, **k):
        if not _STATE["attive"] or _SESSION.get() is not None:
            return await fn(*a, **k)
        for tentativo in range(3):
            async with await _STATE["client"].start_session() as s:
                tok = _SESSION.set(s)
                try:
                    async with s.start_transaction():
                        return await fn(*a, **k)
                except PyMongoError as e:
                    if e.has_error_label("TransientTransactionError") and tentativo < 2:
                        continue
                    raise
                finally:
                    _SESSION.reset(tok)
    return w


CONFLITTO = "Questo documento è stato modificato da un altro utente mentre lo stavi modificando: ricarica la pagina per vedere la versione aggiornata e ripeti la modifica"


def verifica_versione(doc: dict, t: dict) -> dict:
    """Controlla l'intestazione If-Match e restituisce il filtro per l'aggiornamento atomico."""
    cur = int(doc.get("version") or 0)
    hdr = t.get("if_match")
    if hdr not in (None, ""):
        try:
            atteso = int(str(hdr).strip('"'))
        except ValueError:
            raise HTTPException(400, "Versione del documento non valida")
        if atteso != cur:
            raise HTTPException(409, CONFLITTO)
    return {"version": cur} if cur else {"$or": [{"version": {"$exists": False}}, {"version": 0}]}


NUM = {"bsonType": ["double", "int", "long", "decimal"]}
INT = {"bsonType": ["int", "long"]}
STR = {"bsonType": "string"}
DATA = {"bsonType": "string", "pattern": r"^\d{4}-\d{2}-\d{2}"}
SCHEMI = {
    "invoices": {"bsonType": "object", "required": ["id", "company_id", "anno", "numero", "status"], "properties": {
        "id": STR, "company_id": STR, "anno": {**INT, "minimum": 2000, "maximum": 2200}, "numero": {**NUM, "minimum": 1}, "data": DATA,
        "status": {"enum": ["bozza", "inviata", "consegnata", "mancata_consegna", "scartata", "manuale", "storico"]},
        "tipo_documento": {"bsonType": "string", "pattern": r"^TD\d{2}$"}, "totale": NUM}},
    "coa_entries": {"bsonType": "object", "required": ["id", "company_id", "anno", "numero", "data", "righe"], "properties": {
        "id": STR, "company_id": STR, "anno": INT, "numero": {**NUM, "minimum": 1}, "data": DATA, "totale": {**NUM, "minimum": 0},
        "righe": {"bsonType": "array", "minItems": 2, "items": {"bsonType": "object", "required": ["conto", "dare", "avere"], "properties": {
            "conto": STR, "dare": {**NUM, "minimum": 0}, "avere": {**NUM, "minimum": 0}}}}}},
    "payments": {"bsonType": "object", "required": ["id", "company_id", "invoice_id", "importo", "data"], "properties": {
        "id": STR, "company_id": STR, "invoice_id": STR, "importo": {**NUM, "minimum": 0, "exclusiveMinimum": True}, "data": DATA}},
    "passive_payments": {"bsonType": "object", "required": ["id", "company_id", "importo", "data"], "properties": {
        "id": STR, "company_id": STR, "importo": {**NUM, "minimum": 0, "exclusiveMinimum": True}, "data": DATA}},
    "passive_invoices": {"bsonType": "object", "required": ["id", "company_id"], "properties": {
        "id": STR, "company_id": STR, "totale": NUM, "protocollo": {"bsonType": ["int", "long", "null"], "minimum": 1}}},
    "audit_log": {"bsonType": "object", "required": ["id", "at", "method", "path"], "properties": {"id": STR, "at": STR}},
}


async def applica_schemi(db):
    nomi = set(await db.list_collection_names())
    for nome, schema in SCHEMI.items():
        try:
            if nome in nomi:
                await db.command({"collMod": nome, "validator": {"$jsonSchema": schema}, "validationLevel": "moderate", "validationAction": "error"})
            else:
                await db.create_collection(nome, validator={"$jsonSchema": schema}, validationLevel="moderate", validationAction="error")
        except PyMongoError as e:
            log.warning("Regole del database non applicate a %s: %s", nome, e)
