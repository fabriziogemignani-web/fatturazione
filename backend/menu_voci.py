MENU = [
    ("fatture", "Vendite", "Fatture emesse"), ("registro", "Vendite", "Registro numerazione"), ("scadenzario", "Vendite", "Scadenzario clienti"),
    ("comunicazioni", "Vendite", "Comunicazioni ai clienti"), ("ddt", "Vendite", "Documenti di trasporto"), ("fatturazione-differita", "Vendite", "Fatturazione differita"),
    ("riba", "Vendite", "Effetti Ri.Ba."),
    ("registrazione-veloce", "Contabilità generale", "Registrazione veloce documenti"),
    ("passive", "Acquisti", "Fatture ricevute"), ("scadenzario-fornitori", "Acquisti", "Scadenzario fornitori"),
    ("pagamenti-fornitori", "Acquisti", "Pagamenti fornitori"),
    ("registro-iva-vendite", "Fisco e IVA", "Registro IVA vendite"), ("registro-iva-acquisti", "Fisco e IVA", "Registro IVA acquisti"),
    ("liquidazione-iva", "Fisco e IVA", "Liquidazione IVA e F24"), ("bolli-virtuali", "Fisco e IVA", "Bolli virtuali"), ("storico-f24", "Fisco e IVA", "Storico versamenti F24"), ("ritenute", "Fisco e IVA", "Ritenute d'acconto"), ("corrispettivi", "Fisco e IVA", "Corrispettivi"),
    ("esportazione", "Fisco e IVA", "Export commercialista"), ("conservazione", "Fisco e IVA", "Conservazione documenti"),
    ("prima-nota", "Contabilità generale", "Prima nota e giornale"), ("mastrini", "Contabilità generale", "Schede contabili"),
    ("bilancio", "Contabilità generale", "Bilancio di verifica"), ("chiusura", "Contabilità generale", "Chiusura esercizio"),
    ("piano-conti", "Contabilità generale", "Piano dei conti e tabelle"),
    ("riconciliazione", "Tesoreria", "Riconciliazione bancaria"), ("previsione-cassa", "Tesoreria", "Previsione di cassa"),
    ("magazzino", "Magazzino", "Giacenze e movimenti"),
    ("anagrafiche", "Anagrafiche", "Clienti e fornitori"), ("articoli", "Anagrafiche", "Articoli e servizi"),
    ("arch-carica", "Archivio fatture", "Carica fatture"), ("arch-attive", "Archivio fatture", "Fatture attive archiviate"),
    ("arch-passive", "Archivio fatture", "Fatture passive archiviate"), ("arch-anagrafiche", "Archivio fatture", "Clienti e fornitori archivio"),
]
MENU_IDS = {m[0] for m in MENU}
MENU_LABEL = {m[0]: m[2] for m in MENU}

_SIMPLE = {"registro": "registro", "scadenzario": "scadenzario", "scadenzario-passivo": "scadenzario-fornitori",
           "registro-iva-vendite": "registro-iva-vendite", "registro-iva-acquisti": "registro-iva-acquisti",
           "liquidazione-iva": "liquidazione-iva", "corrispettivi": "corrispettivi", "export": "esportazione", "magazzino": "magazzino", "comunicazioni": "comunicazioni", "ritenute": "ritenute", "conservazione": "conservazione", "riba": "riba", "pagamenti-fornitori": "pagamenti-fornitori", "bolli": "bolli-virtuali", "f24-storico": "storico-f24", "reg-veloce": "registrazione-veloce"}
_COGE = {"registrazioni": "prima-nota", "rigenera": "prima-nota", "mastrino": "mastrini", "bilancio": "bilancio", "chiusura": "chiusura",
         "liquidazioni": "liquidazione-iva", "saldaconto": "prima-nota"}


def menu_for(method: str, path: str):
    p = path.removeprefix("/api/").split("/")
    s0, s1 = p[0], (p[1] if len(p) > 1 else "")
    if s0 in _SIMPLE:
        return _SIMPLE[s0]
    if s0 == "ddt":
        return "fatturazione-differita" if s1 == "fatturazione" else "ddt"
    if s0 == "invoices":
        return None if "pagamenti" in p else "fatture"
    if s0 == "clienti":
        return "scadenzario"
    if s0 == "passive":
        return None if "pagamenti" in p else "passive"
    if s0 == "contabilita":
        return _COGE.get(s1) or ("piano-conti" if method != "GET" else None)
    if s0 == "banca":
        return "previsione-cassa" if s1 == "previsione" else "riconciliazione"
    if s0 in ("parties", "articles") and method != "GET":
        return "anagrafiche" if s0 == "parties" else "articoli"
    if s0 == "archivio":
        return {"upload": "arch-carica", "anagrafiche": "arch-anagrafiche"}.get(s1)
    return None


def menu_off(comp: dict, user: dict) -> set:
    off = set(comp.get("menu_off") or [])
    if (user or {}).get("role") != "admin":
        off |= set(user.get("menu_off") or [])
    return off
