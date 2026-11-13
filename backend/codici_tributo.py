from typing import Optional

from fastapi import APIRouter, Depends

CODICI = [
    ("1001", "ritenute", "Ritenute su retribuzioni, pensioni, trasferte, mensilità aggiuntive e relativo conguaglio"),
    ("1002", "ritenute", "Ritenute su emolumenti arretrati"),
    ("1004", "ritenute", "Ritenute sui redditi assimilati a quelli di lavoro dipendente"),
    ("1012", "ritenute", "Ritenute su indennità per cessazione di rapporto di lavoro"),
    ("1019", "ritenute", "Ritenute del 4% operate dal condominio sui corrispettivi (acconto IRPEF)"),
    ("1020", "ritenute", "Ritenute del 4% operate dal condominio sui corrispettivi (acconto IRES)"),
    ("1038", "ritenute", "Ritenute su provvigioni per rapporti di commissione, agenzia, mediazione e rappresentanza"),
    ("1040", "ritenute", "Ritenute su redditi di lavoro autonomo: compensi per l'esercizio di arti e professioni"),
    ("1045", "ritenute", "Ritenute su contributi corrisposti a imprese da regioni, province, comuni e altri enti pubblici"),
    ("1050", "ritenute", "Ritenute su premi riscossi in caso di riscatto di assicurazioni sulla vita"),
    ("1052", "ritenute", "Indennità di esproprio, occupazione e acquisizioni coattive"),
    ("1712", "ritenute", "Acconto dell'imposta sostitutiva sui redditi derivanti dalla rivalutazione del TFR"),
    ("1713", "ritenute", "Saldo dell'imposta sostitutiva sui redditi derivanti dalla rivalutazione del TFR"),
    ("3802", "ritenute", "Addizionale regionale all'IRPEF trattenuta dal sostituto d'imposta"),
    ("3847", "ritenute", "Addizionale comunale all'IRPEF trattenuta dal sostituto d'imposta - acconto"),
    ("3848", "ritenute", "Addizionale comunale all'IRPEF trattenuta dal sostituto d'imposta - saldo"),
    *[(f"60{m:02d}", "iva", f"Versamento IVA mensile - {n}") for m, n in enumerate(
        ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"], 1)],
    ("6013", "iva", "Versamento acconto IVA mensile"),
    ("6031", "iva", "Versamento IVA trimestrale - primo trimestre"),
    ("6032", "iva", "Versamento IVA trimestrale - secondo trimestre"),
    ("6033", "iva", "Versamento IVA trimestrale - terzo trimestre"),
    ("6034", "iva", "Versamento IVA trimestrale - quarto trimestre"),
    ("6035", "iva", "Versamento IVA acconto (contribuenti trimestrali)"),
    ("6099", "iva", "Versamento IVA sulla base della dichiarazione annuale"),
    ("2521", "bollo", "Imposta di bollo sulle fatture elettroniche - primo trimestre"),
    ("2522", "bollo", "Imposta di bollo sulle fatture elettroniche - secondo trimestre"),
    ("2523", "bollo", "Imposta di bollo sulle fatture elettroniche - terzo trimestre"),
    ("2524", "bollo", "Imposta di bollo sulle fatture elettroniche - quarto trimestre"),
    ("2525", "bollo", "Imposta di bollo sulle fatture elettroniche - sanzioni"),
    ("2526", "bollo", "Imposta di bollo sulle fatture elettroniche - interessi"),
    ("4001", "dirette", "IRPEF saldo"),
    ("4033", "dirette", "IRPEF acconto prima rata"),
    ("4034", "dirette", "IRPEF acconto seconda rata o in unica soluzione"),
    ("2001", "dirette", "IRES acconto prima rata"),
    ("2002", "dirette", "IRES acconto seconda rata o in unica soluzione"),
    ("2003", "dirette", "IRES saldo"),
    ("3800", "dirette", "IRAP saldo"),
    ("3812", "dirette", "IRAP acconto prima rata"),
    ("3813", "dirette", "IRAP acconto seconda rata o in unica soluzione"),
    ("1840", "dirette", "Cedolare secca locazioni - acconto prima rata"),
    ("1841", "dirette", "Cedolare secca locazioni - acconto seconda rata o in unica soluzione"),
    ("1842", "dirette", "Cedolare secca locazioni - saldo"),
    ("3850", "altri", "Diritto camerale annuale"),
    ("1668", "interessi", "Interessi per pagamento dilazionato - imposte e ritenute"),
    ("1989", "interessi", "Interessi sul ravvedimento - IRPEF"),
    ("1991", "interessi", "Interessi sul ravvedimento - IVA"),
    ("8904", "sanzioni", "Sanzione pecuniaria IVA"),
    ("8906", "sanzioni", "Sanzione pecuniaria sostituti d'imposta"),
]
CATEGORIE = {"ritenute": "Ritenute e sostituti d'imposta", "iva": "IVA", "bollo": "Imposta di bollo", "dirette": "Imposte dirette",
             "interessi": "Interessi", "sanzioni": "Sanzioni", "altri": "Altri tributi"}
DESCR = {c: d for c, _, d in CODICI}


def descrizione(codice: str) -> str:
    return DESCR.get(codice, f"Codice tributo {codice}")


def build(tenant) -> APIRouter:
    r = APIRouter(prefix="/api/codici-tributo")

    @r.get("")
    async def lista(categoria: Optional[str] = None, q: Optional[str] = None, _: dict = Depends(tenant)):
        k = (q or "").strip().lower()
        return {"categorie": CATEGORIE, "codici": [{"codice": c, "categoria": cat, "categoria_label": CATEGORIE[cat], "descrizione": d} for c, cat, d in CODICI
                                                   if (not categoria or cat == categoria) and (not k or k in c or k in d.lower())]}

    return r
