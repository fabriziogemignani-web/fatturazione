PIANO = [
    ("01", "Immobilizzazioni immateriali"),
    ("01.01", "Costi di impianto e ampliamento"), ("01.01.001", "Costi di impianto e ampliamento"),
    ("01.02", "Software e licenze"), ("01.02.001", "Software e licenze d'uso"),
    ("01.03", "Marchi e brevetti"), ("01.03.001", "Marchi e brevetti"),
    ("01.04", "Avviamento"), ("01.04.001", "Avviamento"),
    ("01.09", "Fondi ammortamento immobilizzazioni immateriali"), ("01.09.001", "F.do amm.to costi di impianto"),
    ("01.09.002", "F.do amm.to software"), ("01.09.003", "F.do amm.to marchi e brevetti"), ("01.09.004", "F.do amm.to avviamento"),
    ("02", "Immobilizzazioni materiali"),
    ("02.01", "Terreni e fabbricati"), ("02.01.001", "Terreni"), ("02.01.002", "Fabbricati"),
    ("02.02", "Impianti e macchinari"), ("02.02.001", "Impianti generici"), ("02.02.002", "Macchinari"),
    ("02.03", "Attrezzature"), ("02.03.001", "Attrezzature industriali e commerciali"),
    ("02.04", "Altri beni materiali"), ("02.04.001", "Mobili e arredi"), ("02.04.002", "Macchine elettroniche d'ufficio"),
    ("02.04.003", "Automezzi"), ("02.04.004", "Beni di costo inferiore a 516,46 euro"),
    ("02.09", "Fondi ammortamento immobilizzazioni materiali"), ("02.09.001", "F.do amm.to fabbricati"), ("02.09.002", "F.do amm.to impianti e macchinari"),
    ("02.09.003", "F.do amm.to attrezzature"), ("02.09.004", "F.do amm.to mobili e arredi"), ("02.09.005", "F.do amm.to macchine d'ufficio"),
    ("02.09.006", "F.do amm.to automezzi"),
    ("03", "Immobilizzazioni finanziarie"),
    ("03.01", "Partecipazioni"), ("03.01.001", "Partecipazioni in altre imprese"),
    ("03.02", "Depositi cauzionali"), ("03.02.001", "Depositi cauzionali attivi"),
    ("04", "Rimanenze"),
    ("04.01", "Rimanenze di magazzino"), ("04.01.001", "Rimanenze materie prime"), ("04.01.002", "Rimanenze prodotti finiti"), ("04.01.003", "Rimanenze merci"),
    ("05", "Crediti"),
    ("05.01", "Crediti verso clienti"), ("05.01.001", "Clienti Italia"), ("05.01.002", "Clienti esteri"), ("05.01.003", "Fatture da emettere"),
    ("05.01.004", "Clienti c/effetti e RiBa"), ("05.01.009", "Fondo svalutazione crediti"),
    ("05.02", "Crediti tributari"), ("05.02.001", "Erario c/IVA"), ("05.02.002", "IVA su acquisti (a credito)"), ("05.02.003", "Erario c/ritenute d'acconto subite"),
    ("05.02.004", "Erario c/acconti IRES"), ("05.02.005", "Erario c/acconti IRAP"), ("05.02.006", "Credito IVA da compensare"),
    ("05.03", "Altri crediti"), ("05.03.001", "Crediti verso dipendenti"), ("05.03.002", "Anticipi a fornitori"), ("05.03.003", "Crediti diversi"),
    ("05.03.004", "INAIL c/crediti"),
    ("06", "Disponibilità liquide"),
    ("06.01", "Banche"), ("06.01.001", "Banca c/c"), ("06.01.002", "Banca c/c secondaria"),
    ("06.02", "Cassa"), ("06.02.001", "Cassa contanti"), ("06.02.002", "Valori bollati"),
    ("06.03", "Carte e conti di pagamento"), ("06.03.001", "Carte prepagate e conti di pagamento"),
    ("07", "Ratei e risconti attivi"),
    ("07.01", "Ratei e risconti attivi"), ("07.01.001", "Ratei attivi"), ("07.01.002", "Risconti attivi"),
    ("10", "Patrimonio netto"),
    ("10.01", "Capitale"), ("10.01.001", "Capitale sociale"),
    ("10.02", "Riserve"), ("10.02.001", "Riserva legale"), ("10.02.002", "Riserva straordinaria"), ("10.02.003", "Versamenti soci in c/capitale"),
    ("10.03", "Risultato"), ("10.03.001", "Utili (perdite) portati a nuovo"), ("10.03.002", "Utile (perdita) d'esercizio"),
    ("11", "Fondi per rischi e oneri"),
    ("11.01", "Fondi per rischi e oneri"), ("11.01.001", "Fondo imposte"), ("11.01.002", "Fondo rischi diversi"),
    ("12", "Trattamento di fine rapporto"),
    ("12.01", "Fondo TFR"), ("12.01.001", "Fondo trattamento di fine rapporto"),
    ("13", "Debiti"),
    ("13.01", "Debiti verso banche"), ("13.01.001", "Banca c/anticipi"), ("13.01.002", "Mutui passivi"), ("13.01.003", "Finanziamenti bancari"),
    ("13.02", "Debiti verso fornitori"), ("13.02.001", "Fornitori Italia"), ("13.02.002", "Fornitori esteri"), ("13.02.003", "Fatture da ricevere"),
    ("13.03", "Debiti tributari"), ("13.03.001", "IVA su vendite (a debito)"), ("13.03.002", "Erario c/ritenute lavoratori autonomi"),
    ("13.03.003", "Erario c/ritenute lavoratori dipendenti"), ("13.03.004", "Debiti per IRES"), ("13.03.005", "Debiti per IRAP"),
    ("13.03.006", "IVA split payment da versare"),
    ("13.04", "Debiti previdenziali"), ("13.04.001", "INPS c/contributi"), ("13.04.002", "INAIL c/contributi"), ("13.04.003", "Casse previdenziali professionali"),
    ("13.05", "Altri debiti"), ("13.05.001", "Dipendenti c/retribuzioni"), ("13.05.002", "Soci c/finanziamenti"), ("13.05.003", "Debiti diversi"),
    ("13.05.004", "Clienti c/anticipi"), ("13.05.009", "Conto transitorio da sistemare"),
    ("14", "Ratei e risconti passivi"),
    ("14.01", "Ratei e risconti passivi"), ("14.01.001", "Ratei passivi"), ("14.01.002", "Risconti passivi"),
    ("20", "Valore della produzione"),
    ("20.01", "Ricavi delle vendite e delle prestazioni"), ("20.01.001", "Ricavi vendite merci"), ("20.01.002", "Ricavi prestazioni di servizi"),
    ("20.01.003", "Ricavi vendite prodotti"), ("20.01.004", "Ricavi per contributo cassa previdenza"), ("20.01.005", "Ricavi da corrispettivi"),
    ("20.01.009", "Resi e sconti su vendite"),
    ("20.02", "Variazione rimanenze prodotti"), ("20.02.001", "Variazione rimanenze prodotti finiti"),
    ("20.05", "Altri ricavi e proventi"), ("20.05.001", "Rimborsi spese"), ("20.05.002", "Plusvalenze"), ("20.05.003", "Sopravvenienze attive"),
    ("20.05.004", "Contributi in conto esercizio"), ("20.05.005", "Arrotondamenti attivi"),
    ("30", "Costi della produzione"),
    ("30.06", "Materie prime, sussidiarie e merci"), ("30.06.001", "Merci c/acquisti"), ("30.06.002", "Materie prime c/acquisti"),
    ("30.06.003", "Materiale di consumo"), ("30.06.004", "Cancelleria e stampati"), ("30.06.005", "Carburanti e lubrificanti"),
    ("30.07", "Costi per servizi"), ("30.07.001", "Lavorazioni di terzi"), ("30.07.002", "Trasporti"), ("30.07.003", "Energia elettrica"),
    ("30.07.004", "Gas e acqua"), ("30.07.005", "Telefonia e internet"), ("30.07.006", "Consulenze tecniche e professionali"),
    ("30.07.007", "Consulenze amministrative e fiscali"), ("30.07.008", "Manutenzioni e riparazioni"), ("30.07.009", "Assicurazioni"),
    ("30.07.010", "Pubblicità e promozione"), ("30.07.011", "Spese e commissioni bancarie"), ("30.07.012", "Viaggi e trasferte"),
    ("30.07.013", "Compensi amministratori"), ("30.07.014", "Pulizie"), ("30.07.015", "Servizi diversi"), ("30.07.016", "Software e servizi cloud"),
    ("30.08", "Godimento beni di terzi"), ("30.08.001", "Affitti passivi"), ("30.08.002", "Canoni di leasing"), ("30.08.003", "Noleggi"),
    ("30.09", "Costi per il personale"), ("30.09.001", "Salari e stipendi"), ("30.09.002", "Oneri sociali"), ("30.09.003", "Accantonamento TFR"),
    ("30.09.004", "Altri costi del personale"),
    ("30.10", "Ammortamenti e svalutazioni"), ("30.10.001", "Ammortamento immobilizzazioni immateriali"),
    ("30.10.002", "Ammortamento immobilizzazioni materiali"), ("30.10.003", "Svalutazione crediti"),
    ("30.11", "Variazione rimanenze materie e merci"), ("30.11.001", "Variazione rimanenze merci"),
    ("30.14", "Oneri diversi di gestione"), ("30.14.001", "Imposte e tasse diverse"), ("30.14.002", "Valori bollati e imposta di bollo"),
    ("30.14.003", "Sanzioni e multe"), ("30.14.004", "Minusvalenze"), ("30.14.005", "Sopravvenienze passive"), ("30.14.006", "Arrotondamenti passivi"),
    ("30.14.007", "Abbonamenti e quote associative"),
    ("40", "Proventi e oneri finanziari"),
    ("40.01", "Proventi finanziari"), ("40.01.001", "Interessi attivi bancari"), ("40.01.002", "Altri proventi finanziari"),
    ("40.02", "Oneri finanziari"), ("40.02.001", "Interessi passivi bancari"), ("40.02.002", "Interessi passivi su mutui"),
    ("40.02.003", "Interessi su versamenti IVA trimestrali"), ("40.02.004", "Altri oneri finanziari"),
    ("50", "Imposte sul reddito"),
    ("50.01", "Imposte dell'esercizio"), ("50.01.001", "IRES"), ("50.01.002", "IRAP"),
    ("60", "Conti di chiusura"),
    ("60.01", "Conti di apertura e chiusura"), ("60.01.001", "Stato patrimoniale di apertura"), ("60.01.002", "Stato patrimoniale di chiusura"),
    ("60.01.003", "Conto economico"),
]

TIPI = {"attivita": "Attività", "passivita": "Passività e netto", "costo": "Costi", "ricavo": "Ricavi", "chiusura": "Conti di chiusura"}


def tipo_conto(codice: str) -> str:
    m = codice[:2]
    if codice.startswith("40.01"):
        return "ricavo"
    if codice.startswith("40.02") or m in ("30", "50"):
        return "costo"
    if m == "40":
        return "ricavo"
    if m == "20":
        return "ricavo"
    if m == "60":
        return "chiusura"
    return "attivita" if m < "10" else "passivita"


CAUSALI = [
    ("FV", "Fattura di vendita", "vendite"), ("NV", "Nota di credito a cliente", "vendite"),
    ("FA", "Fattura di acquisto", "acquisti"), ("NA", "Nota di credito da fornitore", "acquisti"),
    ("IN", "Incasso da cliente", "nessuno"), ("PG", "Pagamento a fornitore", "nessuno"),
    ("VC", "Versamento corrispettivi in banca", "nessuno"), ("VI", "Versamento IVA", "nessuno"),
    ("MB", "Movimento bancario", "nessuno"), ("GC", "Giroconto", "nessuno"), ("LI", "Liquidazione IVA", "nessuno"),
    ("AM", "Ammortamenti", "nessuno"), ("RR", "Ratei e risconti", "nessuno"), ("ST", "Stipendi e contributi", "nessuno"),
    ("AP", "Apertura conti", "nessuno"), ("CH", "Chiusura conti", "nessuno"), ("GE", "Operazione generica", "nessuno"),
]

_NAT = [("N1", "Escluse art. 15"), ("N2.1", "Non soggette artt. 7-7septies"), ("N2.2", "Non soggette altri casi"),
        ("N3.1", "Non imponibili esportazioni"), ("N3.2", "Non imponibili cessioni intracomunitarie"), ("N3.3", "Non imponibili verso San Marino"),
        ("N3.4", "Non imponibili assimilate"), ("N3.5", "Non imponibili a seguito di dichiarazione d'intento"), ("N3.6", "Non imponibili altre"),
        ("N4", "Esenti"), ("N5", "Regime del margine"), ("N6.1", "Reverse charge rottami"), ("N6.2", "Reverse charge oro e argento"),
        ("N6.3", "Reverse charge subappalto edilizia"), ("N6.4", "Reverse charge cessione fabbricati"), ("N6.5", "Reverse charge telefonia"),
        ("N6.6", "Reverse charge prodotti elettronici"), ("N6.7", "Reverse charge prestazioni comparto edile"), ("N6.8", "Reverse charge settore energetico"),
        ("N6.9", "Reverse charge altri casi"), ("N7", "IVA assolta in altro stato UE")]
CODICI_IVA = [(str(a), f"IVA {a}%", float(a), None, False) for a in (22, 10, 5, 4)] + [(n, d, 0.0, n, n.startswith("N6")) for n, d in _NAT]

RUOLI = [
    ("clienti", "Crediti verso clienti"), ("fornitori", "Debiti verso fornitori"),
    ("ricavi", "Contropartita ricavi di vendita (unica)"), ("ricavi_cassa", "Ricavi per contributo cassa previdenza"),
    ("costi", "Contropartita costi di acquisto (unica)"),
    ("iva_vendite", "IVA sulle vendite (a debito)"), ("iva_acquisti", "IVA sugli acquisti (a credito)"), ("iva_split", "IVA split payment da versare"),
    ("ritenute_subite", "Ritenute d'acconto subite"), ("ritenute_operate", "Ritenute d'acconto da versare"),
    ("banca", "Banca"), ("cassa", "Cassa contanti"), ("erario_iva", "Erario c/IVA (versamenti)"),
    ("transitorio", "Conto transitorio (importi non abbinati)"), ("arr_attivi", "Arrotondamenti attivi"), ("arr_passivi", "Arrotondamenti passivi"),
]

PARAMETRI = {
    "clienti": "05.01.001", "fornitori": "13.02.001", "ricavi": "20.01.001", "ricavi_cassa": "20.01.004", "costi": "30.06.001",
    "iva_vendite": "13.03.001", "iva_acquisti": "05.02.002", "iva_split": "13.03.006", "ritenute_subite": "05.02.003",
    "ritenute_operate": "13.03.002", "banca": "06.01.001", "cassa": "06.02.001", "erario_iva": "05.02.001", "transitorio": "13.05.009",
    "arr_attivi": "20.05.005", "arr_passivi": "30.14.006",
    "contropartita_vendite": "unica", "contropartita_acquisti": "unica", "aliquota_rc": 22.0,
    "categorie": {"Spese e commissioni bancarie": "30.07.011", "Stipendi e contributi": "13.05.001", "F24 altri tributi": "13.03.003",
                  "Giroconto tra conti": "06.01.002", "Finanziamenti e mutui": "13.01.003", "Prelievo / versamento contanti": "06.02.001",
                  "Altro": "13.05.009"},
}
