# PRD – Fatturazione Elettronica (FatturaPA / SDI)

## Original problem statement
"da progetto fe archivio duplica in un clone per implementare in sistema di fatturazione elettonica"
(Source project "FE archivio" not present in workspace → user chose to rebuild from scratch.)

User choices: create invoices + FatturaPA XML; clienti/fornitori registry; PDF print; SDI sending via intermediary (SIMULATED for now, connect later); multi-user company access with Google login.

## Architecture
- FastAPI (`server.py`, `fatturapa.py` XML builder/totals) + MongoDB (users, user_sessions, company, parties, invoices, counters)
- React + shadcn; Emergent-managed Google Auth (httpOnly cookie)
- Owner admin: ADMIN_EMAIL=fabrizio.gemignani@gmail.com; other users pending until approved

## Personas
- Admin (owner): everything incl. users and company data
- Contabile: invoices + send to SDI
- Operatore: drafts and anagrafiche, no SDI send

## Core requirements
- Company (cedente) data, regime fiscale, IBAN
- Clienti/Fornitori CRUD with P.IVA/CF/Codice destinatario/PEC validation
- Invoices TD01/TD04/TD05/TD06, lines with IVA 22/10/5/4/0 + Natura, progressive numbering per year
- FatturaPA FPR12 XML preview/download, filename IT<piva>_<progressivo>.xml
- Printable invoice (browser print → PDF)
- SDI flow bozza → inviata → consegnata/scartata (SIMULATED)

## Implemented (2026-10-29)
- All above; dashboard KPIs, monthly chart, status counts
- Fixes after test iteration 1: date validation (422), unique (anno,numero) index + retry, date ≥ last invoice, only last bozza deletable, new progressivo on resend, admin cannot modify self, toasts bottom-right

## Implemented (2026-10-29, iteration 2)
- Email/password registration (always pending until admin approval), login with lockout (5 tries/15 min per email), password recovery via Emergent managed email (1h single-use link)
- Security: no auto-admin on email registration; Google login removes unverified passwords; admin promoted only via Google or password reset
- Ritenuta d'acconto (RT01-RT06, aliquota, causale 770) and cassa previdenziale (TC01-TC22, aliquota, IVA, soggetta a ritenuta); netto a pagare; XML DatiRitenuta / DatiCassaPrevidenziale; company defaults
- Archivio articoli/servizi (codice unico, U.M., prezzo, IVA/natura), insert into invoice
- Client VAT regime (esenzione natura + riferimento normativo); dichiarazione d'intento N3.5 with mandatory protocollo + data, XML AltriDatiGestionali INTENTO
- Invoice date cannot be in the future

## Implemented (2026-10-29, iteration 3)
- Gestione utenti: admin creates users (approved, optional 72h invite email), edits name/role, deletes, sends password link, filters/search, access column; owner/self protected
- SDI notifications (SIMULATED): IN, RC consegnata, MC mancata consegna, NS scarto; dashboard "Cruscotto fatture inviate" per notifica with counts, amounts, latest notifications, click-through to filtered invoice list

## Implemented (2026-10-29, iteration 4)
- Multi-company: companies collection; all data scoped by X-Company-Id (validated server-side against user.company_ids; admin sees all); per-company numbering/progressivo; Aziende page (create/open/delete), sidebar switcher, user ↔ company assignment in Gestione utenti; automatic migration of old single company data; multi-tab sync

## Implemented (2026-10-29, iteration 5)
- Note di credito TD04: separate register per company/year (n/NC/anno), "Crea nota di credito" from sent invoice (prefill), link to original (DatiFattureCollegate in XML), residual check on create/update/send, linked NC list + residuo on original, list filter Fatture/NC, NC net of fatturato on dashboard, print reference
- Storno parziale rapido: dialog on sent invoice with modes tutta / righe selezionate / percentuale (presets 10-25-50% or custom), live total vs residuo, prefilled NC
- Storno totale automatico: POST /api/invoices/{id}/storno-totale {invia} creates full NC (lines, cassa, ritenuta, today) and optionally sends it to SDI (admin/contabile); blocked if NCs already linked
- Storno da elenco: quick button (Zap) on sent invoices without NC in the list -> confirm dialog (optional immediate SDI send) -> creates the TD04 credit note document and opens it; badge "stornata" on reversed invoices (list returns has_nc)

## Implemented (2026-10-29, iteration 6)
- Numero documento modificabile in bozza (create/update, campo "numero" opzionale): unico per registro/anno, max = ultimo+1 (registro vuoto: numero iniziale libero), data coerente con documento precedente/successivo
- Documenti inviati allo SDI (qualsiasi stato ≠ bozza, scartata inclusa) non modificabili né eliminabili; scartata solo reinviabile

## Implemented (2026-10-29, iteration 7)
- Correzione scartate: PUT consentito su stato scartata (stesso numero, storico "Corretta dopo lo scarto"), poi reinvio; eliminazione sempre vietata dopo l'invio
- Registro numerazione (/registro, GET /api/registro): sequenza per anno e registro (Fatture/NC), numeri liberi con intervallo date e "Usa questo numero", prossimo numero
- Clienti PA: flag pubblica_amministrazione (Codice Univoco Ufficio a 6 caratteri, XML FPA12), split payment opzionale (EsigibilitaIVA S, netto senza IVA)
- Fattura PA: riferimento ordine/contratto/convenzione + data, CIG (10) e CUP (15) in XML (DatiOrdineAcquisto…) e in stampa; copiati nello storno totale
- Campo quantità più largo (anche su mobile)

## Implemented (2026-10-29, iteration 8)
- Ricerca Indice PA nell'anagrafica cliente PA (GET /api/ipa/search, open data IndicePA "Unità organizzative che ricevono fatture elettroniche", nessuna chiave): compila codice univoco ufficio, denominazione, CF, indirizzo, CAP, PEC

## Implemented (2026-10-29, iteration 9)
- Errori per campo: backend restituisce detail=[{loc:[body,campo], msg IT}] (FieldError nei model validator, ferr() negli errori di business, handler RequestValidationError con messaggi tradotti)
- Frontend: Field(name) + useFieldErrors/FieldErrors → bordo rosso, testo errore sotto il campo, scroll al campo, toast "Correggi i N campi evidenziati in rosso"; righe fattura con "Riga N:"; reset alla digitazione/selezione

## Implemented (2026-10-29, iteration 10)
- Scadenzario clienti: rate per fattura (RateCard: genera N rate ogni X gg / fine mese; somma = netto; XML TP01 con DettaglioPagamento per rata + IBAN), incassi parziali (collection payments), allocazione FIFO sulle rate, stati pagata/parziale/aperta/scaduta
- Compensazione note di credito: NC collegata compensa automaticamente la sua fattura; credito residuo compensabile manualmente su altre fatture dello stesso cliente (metodo "compensazione")
- Pagina /scadenzario (KPI, filtro cliente, tab, Incassa/Compensa), pannello incassi nell'editor, pannello "Scadenze per cliente" in dashboard
- API: GET /api/scadenzario, GET/POST /api/invoices/{id}/pagamenti, DELETE /api/pagamenti/{id} (scrittura solo admin/contabile)

## Implemented (2026-10-29, iteration 11)
- Estratto conto cliente PDF (reportlab, estratto.py): movimenti dare/avere con saldo progressivo, compensazioni NC, partite aperte/scadute, totali, IBAN — GET /api/clienti/{pid}/estratto-conto.pdf
- Sollecito pagamento manuale: anteprima (GET /api/clienti/{pid}/sollecito) e invio (POST, admin/contabile) via email gestita con estratto conto PDF allegato; destinatario email o PEC del cliente; max 3/24h; storico in db.solleciti
- UI: pulsanti "Estratto conto" e "Sollecito" nello Scadenzario filtrato per cliente
- Estratto conto PDF anche da Anagrafica: icona su ogni riga cliente e pulsante nella scheda cliente (PartyDialog)
- Anagrafica clienti: colonne Saldo aperto (link allo scadenzario, prossima scadenza, crediti NC) e Scaduto; righe dei clienti in ritardo evidenziate in rosso con badge e filtro "clienti in ritardo"

## Implemented (2026-10-30)
- Note di riga fattura (campo `note` su LineIn, max 500): icona nota su ogni riga nell'editor, stampa sotto la descrizione, XML come AltriDatiGestionali TipoDato "NOTA" (blocchi da 60 caratteri), copiate negli storni

## Implemented (2026-10-30, iteration 12)
- Fatture passive: ricezione SDI SIMULATA (fornitori DEMO, POST /api/passive/sdi-sync) + caricamento file XML/P7M (CAdES DER o base64, POST /api/passive/upload, max 20 file da 5 MB); parser FatturaPA (passive.py), controllo destinatario = azienda, duplicati (hash e fornitore+numero+data), XML originale conservato (base64)
- Fornitore creato in automatico in anagrafica (origine fattura_passiva), NC ricevute collegate alla fattura (anche se arrivano prima)
- Stato registrazione (da registrare / registrata / contestata) con note; vista leggibile stampabile/PDF e download XML (/passive/:id)
- Scadenzario fornitori (/scadenzario-fornitori, GET /api/scadenzario-passivo): rate modificabili, pagamenti parziali, compensazione con NC ricevute; contestate escluse; pannello "Scadenze per fornitore" in dashboard
- Menu laterale diviso in sezioni: Fatture attive (Fatture emesse, Registro numerazione, Scadenzario clienti), Fatture passive (Fatture ricevute, Scadenzario fornitori), Archivi, Impostazioni
- Registro IVA acquisti (/registro-iva-acquisti, GET /api/registro-iva-acquisti?anno&dal&al): fatture ricevute "registrata" in ordine di protocollo (assegnato al passaggio a registrata, progressivo per anno; rimosso se si torna indietro), righe per aliquota/natura, NC in negativo, riepilogo per aliquota, filtro anno/trimestre/mese, stampa/PDF con intestazione azienda
- Data di registrazione scelta dall'utente (tra data documento e oggi; vuota = oggi)
- Registro IVA vendite (/registro-iva-vendite, GET /api/registro-iva-vendite): fatture/NC emesse inviate allo SDI, stessi totali per aliquota, IVA split evidenziata, stampa
- Liquidazione IVA (/liquidazione-iva, GET /api/liquidazione-iva?anno&periodicita=mensile|trimestrale): debito vendite (esclusa IVA split) − credito acquisti registrati, credito riportato (anche dall'anno precedente), interessi 1% trimestrali T1–T3, soglia 25,82 € rinviata al periodo successivo, prospetto stampabile

## Implemented (2026-10-31, iteration 13)
- Reverse charge fatture ricevute (Natura N6.x): in registrazione si sceglie l'aliquota di integrazione (22/10/5/4, default 22); salvato reverse_charge [{idx, natura, imponibile, aliquota, imposta}] (idx = posizione nel riepilogo), cancellato se si annulla la registrazione
- Registro IVA acquisti: righe RC con IVA integrata, totali "N6.x RC aliquota", imposta_rc; NC in negativo
- Liquidazione IVA: IVA RC sommata sia a debito (colonna "Reverse charge a debito") sia a credito (detrazione piena)

## Implemented (2026-10-31, iteration 14-15)
- Scadenzario clienti/fornitori: ordinamento per data (crescente/decrescente), raggruppamento per mese con totale, filtro periodo (prossimi 7/30/60/90 gg, questo mese, mese prossimo, personalizzato dal/al), totale filtrato
- Corrispettivi giornalieri (db.corrispettivi): ricezione dal cassetto fiscale SIMULATA (POST /api/corrispettivi/sync: giorni mancanti fino a ieri, domeniche escluse, max 62 gg indietro; IVA scorporata 22/10/4), registro stampabile /corrispettivi (GET /api/corrispettivi?anno&dal&al, totali per aliquota, eliminazione giorno), pannello dashboard incassi (GET /api/corrispettivi/riepilogo), IVA corrispettivi a debito nella liquidazione (colonna dedicata)

## Backlog
- P0: real intermediary (OpenAPI / Aruba / Fatture in Cloud) for send + notifications; real cassetto fiscale corrispettivi (servizio a pagamento o import file XML)

## Implemented (2026-11-02, iteration 16) – Self-hosting
- Accesso solo email e password (login Google rimosso). Admin creato all'avvio da ADMIN_EMAIL/ADMIN_PASSWORD se manca (non sovrascrive password esistenti). COOKIE_SECURE=false per http interno
- SMTP per azienda (password cifrata con SMTP_ENCRYPTION_KEY) in Dati azienda; GET/PUT/DELETE /api/company/smtp, POST /api/company/smtp/test. Solleciti con SMTP dell'azienda; inviti/recupero password con SMTP della prima azienda dell'utente (o prima configurata). Errori SMTP 400 in italiano
- Pacchetto installazione deploy/ (docker-compose mongo+backend+nginx, Dockerfile, nginx.conf, .env.example, requirements senza librerie Emergent) e guida /app/INSTALLAZIONE.md
- Cambio password dal menu laterale: POST /api/auth/change-password {current_password,new_password>=8}; verifica password attuale (5 errori -> blocco 15 min), chiude le altre sessioni dell'utente
- Installazione su Windows senza Docker: guida /app/INSTALLAZIONE_WINDOWS.md (Git, Python 3.11, Node 20, MongoDB servizio, nginx per Windows, NSSM per i servizi FatturazioneBackend/FatturazioneWeb, firewall, backup schtasks, aggiornamenti) e file deploy/windows/ (nginx.conf, backend.env.example, avvia-backend.bat, aggiorna.bat, backup.bat, .gitattributes CRLF). Rimosso jq da deploy/requirements.txt (senza pacchetti per Windows)

## Implemented (2026-11-05, iteration 20) – Banche aziendali
- Company.banche [{id, nome, iban, abi, cab, bic, predefinita}] max 20: IBAN validato (mod 97, IT 27 caratteri), ABI/CAB ricavati dall'IBAN italiano (errore campo se non coincidono), BIC 8/11, IBAN duplicato -> errore campo, una sola predefinita; company.iban = IBAN predefinito (usato da solleciti/estratto). Payload legacy con solo iban -> convertito in una banca
- Fattura: banca_id (scelta in "Pagamento e note" per Bonifico MP05 / RIBA MP12, predefinita preselezionata), snapshot `banca` salvato sulla fattura; XML DettaglioPagamento con IstitutoFinanziario, IBAN, ABI, CAB, BIC; copia di cortesia con coordinate bancarie
- Pending (not answered by user): scelta intermediario SDI/conservazione con configurazione per azienda (A-Cube / Openapi / Aruba / altro), notifiche via polling o webhook

## Implemented (2026-11-05, iteration 21) – Archivio fatture (progetto importfatture integrato)
- Area separata "Archivio fatture" (selettore nel menu laterale: Fatturazione / Archivio fatture) con menu proprio: Dashboard archivio, Carica fatture (solo admin/contabile), Fatture attive, Fatture passive, Clienti e fornitori
- Backend backend/archivio.py (router /api/archivio/*) + archivio_parser.py; collezioni separate arch_invoices / arch_anagrafiche per company_id (nessun dato mischiato con fatture e passive della fatturazione)
- Caricamento massivo XML / P7M (asn1crypto, niente openssl) / ZIP annidati / cartelle (drag&drop), lotti da 10, esito per file, duplicati; classificazione attiva/passiva da P.IVA/CF azienda; data AAAA-MM-GG obbligatoria; XML >12 MB salvato senza contenuto allegati
- Elenchi per anno con ordinamento protocollo, ricerca, filtro tipo documento, paginazione, totale, export CSV; dettaglio leggibile + download XML + eliminazione; anagrafiche archivio per ruolo con riepilogo per anno; statistiche dashboard
- Nessuna migrazione dati dal vecchio progetto (richiesta utente)

## Implemented (2026-11-05, iteration 22) – Moduli per azienda
- company.moduli {fatturazione, archivio, fatture_attive, fatture_passive, corrispettivi} (default tutti attivi); PUT /api/companies/{id}/moduli solo admin globale; validazione: almeno un'area, e con Fatturazione almeno una funzione
- Blocco lato server nella dipendenza tenant (403 "Modulo non attivo per questa azienda") per segmento URL: archivio, corrispettivi, passive*, invoices/pagamenti/scadenzario/registri/clienti, dashboard/liquidazione/parties/articles/ipa; /company e SMTP sempre ammessi
- Frontend: pulsante "Moduli" sulle schede in Aziende (dialog con interruttori), menu e selettore aree filtrati, redirect delle pagine non attive, dashboard e anagrafiche nascondono le parti di moduli spenti; Impostazioni sempre visibili anche nell'area Archivio

## Implemented (2026-11-05, iteration 23) – Permessi per utente
- user.moduli (stessi flag delle aziende), PUT /api/users/{id}/moduli (solo admin, non su se stessi/titolare, stessa validazione)
- Moduli effettivi = moduli azienda AND moduli utente (gli admin non hanno restrizioni); applicati in tenant() e in GET /api/companies per i non admin
- Gestione utenti: colonna "Moduli" con dialog a interruttori; testing iteration_23: 26/26 backend, frontend 100%
- Aggiornamento server Windows: deploy\windows\aggiorna.bat dopo "Save to GitHub" (git pull + build)

## Implemented (2026-11-05, iteration 24) – Aggiornamento dal programma
- backend/updater.py: GET /api/system/update-status (confronta git HEAD locale con l'ultimo commit su GitHub, controllo ogni 24h, env opzionali UPDATE_REPO/UPDATE_BRANCH/GITHUB_TOKEN; senza UPDATE_REPO disattivo), POST /api/system/update (tutti gli utenti approvati; solo Windows; avvia l'attività pianificata come SYSTEM)
- deploy/windows/aggiorna-auto.bat: backup (annulla se fallisce) → stop servizi → git pull con token → .env frontend vuoto → pip → yarn build → riavvio; stato in logs\aggiornamento.stato, log in logs\aggiornamento.log
- Frontend UpdateBanner: bottone rosso in basso, avviso di interruzione, overlay con polling e ricarica automatica
- Verificato: logica di stato con un repository pubblico e interfaccia (stato simulato); esecuzione reale sul server Windows non provabile qui
- Novità della versione: lo stato include "changes" (commit tra versione installata e GitHub, API compare, max 50, più recenti prima, esclusi auto-commit); l'avviso mostra l'elenco con le date

## Implemented (2026-11-05, iteration 24) – Collegamento SDI reale (Openapi.it / A-Cube)
- company.sdi {provider simulato|openapi|acube, ambiente sandbox|production, token_enc / email + password_enc (Fernet), last_sync_at/error}; GET /api/company/sdi (tutti), PUT + POST /test (admin); segreti mai restituiti
- backend/sdi_providers.py: invio XML, notifiche (RC/NS/MC/NE/DT/AT → stati), fatture ricevute + download XML
- Invio fattura usa il provider se configurato (errore → resta bozza); "Aggiorna stato SDI" legge le notifiche; "Scarica da SDI" importa le passive (origine "sdi"); controllo automatico ogni 15 minuti
- UI: card "Collegamento SDI" in Dati azienda; nota in Fatture ricevute. Testing iteration_24: 22/22 backend (successi con provider simulato via mock), frontend 100%. Non provato con credenziali reali

## Implemented (2026-11-05, iteration 25) – Ricezione pianificata dallo SDI
- company.sdi_schedule {enabled, modo intervallo|orari, ogni_minuti, dalle, alle, orari[], giorni[0-6], passive, notifiche, next_run_at, last_run}; orari in Europe/Rome (backend/sdi_schedule.py; tzdata aggiunto a deploy/requirements.txt)
- GET /api/company/sdi-schedule (tutti), PUT (admin), POST /run (admin/contabile); scheduler in-app ogni 60s con claim atomico (sostituisce il vecchio ciclo fisso di 15 minuti)
- UI: card "Ricezione pianificata dallo SDI" in Dati azienda; pannello "Ricezione dallo SDI" in dashboard (prossima/ultima esecuzione, conteggi, errori, Esegui ora)
- Testing iteration_25: 20/20 + 22/22 regressione backend, frontend 100%

## Implemented (2026-11-05, iteration 26) – Export per il commercialista
- backend/export_comm.py: PDF di cortesia server-side (reportlab) per emesse e ricevute, riepilogo Excel (openpyxl, 2 fogli), ZIP (Fatture_emesse/XML+PDF, Fatture_ricevute/XML+PDF, Riepilogo.xlsx)
- GET /api/export/commercialista (conteggi, totali, ultimo email, log), GET .zip, POST /send (SMTP aziendale, max 20 MB, salva company.commercialista_email, db.export_log); admin/contabile; emesse = inviata/consegnata/mancata_consegna; rispetta i moduli
- emailer: allegati con mime configurabile (default PDF). Dipendenze openpyxl/et_xmlfile aggiunte a deploy/requirements.txt
- Pagina /esportazione (menu IVA → "Export commercialista"). Testing iteration_26: 13/15 → corretta la validazione delle date impossibili (verificata con curl)

## Implemented (2026-11-05, iteration 27-28) – Riconciliazione bancaria (PSD2 A-Cube + file)
- backend/banca.py: parser CSV italiani (Dare/Avere o Importo, preambolo, 1.234,56) e CBI RH (record 61/62/63/64, saldo da 64); client A-Cube Open Banking (ob-sandbox / ob, login common.api); punteggio abbinamento (importo, numero fattura con anno, nome controparte), auto solo se ≥80, con nome e senza alternative ≥50
- Collezioni bank_accounts, bank_tx (unique company_id+ext_id). Endpoints /api/banca/*: config (admin, password cifrata, fallback credenziali SDI A-Cube), conti, import file, psd2 connect/reconnect/sync, movimenti, candidati, riconcilia (incasso/pagamento multi-fattura con creazione pagamenti, corrispettivi, IVA F24, altro con categoria), annulla, ignora, auto, riepilogo. Sync automatica ogni 6 ore nel ciclo pianificato
- Cancellare un pagamento creato dalla banca riporta il movimento da riconciliare (e rimuove i pagamenti collegati)
- UI: menu Tesoreria → Riconciliazione bancaria; pannello Banca in dashboard. Testing iteration_28: 35/35 bank suite + regressione OK

## Implemented (2026-11-07, iteration 29) – Regole di abbinamento e Previsione di cassa
- db.bank_rules {nome, contiene (spazio = tutte le parole, virgola = alternative), segno, importo_min/max, categoria, note, attiva, applicata}; CRUD /api/banca/regole + /prova; applicate in _auto_match solo se non c'è una fattura sicura; "Crea regola" dal dialog Abbina (tipo Altro) con riconciliazione immediata dei movimenti simili
- GET /api/banca/previsione?giorni&scaduti: saldo conti + rate aperte clienti (+) e fornitori (−), scadute contate a oggi, serie giornaliera, minimo, avviso conti senza saldo
- UI: dialog "Regole" in Riconciliazione; pagina /previsione-cassa (Tesoreria) con grafico; link nel pannello Banca della dashboard
- Testing: backend test_iteration29 18/18 + test_iteration27 35/35; frontend iteration_29 95% → corretti overflow mobile del dialog, etichetta duplicata, asse del grafico, plurali

## Implemented (2026-11-07, iteration 30) – Magazzino e sottoscorta
- backend/magazzino.py: db.stock_moves (carico/scarico/rettifica ±, causali per tipo, documento, note); costo medio ponderato ricalcolato a ogni movimento (articles.giacenza, costo_medio, valore_magazzino); blocco giacenza negativa anche retrodatata; DELETE solo admin/contabile
- ArticleIn: gestione_magazzino, scorta_minima, scorta_riordino (quantità di riordino), fornitore_abituale; non si disattiva la gestione né si elimina un articolo con movimenti; modifica articolo aggiorna i movimenti
- Endpoints /api/magazzino/articoli, sottoscorta (da ordinare = max(riordino, minima − giacenza)), movimenti (giacenza_dopo), riepilogo
- UI: Articoli con sezione Magazzino e riquadro Sottoscorta; pagina /magazzino (Giacenze, Movimenti, Sottoscorta); pannello Magazzino in dashboard. Testing iteration_30: backend 18/18, frontend 100%










- P1: digital signature/conservazione sostitutiva; detraibilità parziale/pro-rata IVA acquisti; export commercialista
- P2: bollo virtuale; autofatture TD16-TD19 XML

## 2026-11-09 — Windows server sync
- New Windows server aligned to GitHub main (f1d0631) via `git fetch` + `git reset --hard origin/main` + `aggiorna.bat`; user confirmed all working.


## 2026-11-09 — Contabilità generale + menu riorganizzato
- Request: "aggiungi un modulo di contabilità generale dove si possa gestire con causali contabili, codici Iva e un piano dei conti che puoi caricare tu in automatico le registrazioni in partita doppia. le fatture di vendita devono essere registrate in automatico. La contropartita può essere una sola inserita nei parametri di configurazione dell'azienda oppure tramite scelta aggiungi all'anagrafica dell'articolo un campo dove viene inserita la contropartita di vendita. Gli acquisti vanno allo stesso modo delle vendite solo che il campo lo aggiungi nel fornitore" + "riorganizza anche i menu raggruppando per aree omogenee".
- backend/contabilita.py + contabilita_dati.py: standard PMI chart (~205 accounts, 3 levels), 17 causali, 25 codici IVA, parametri per company (seeded lazily). Collections coa_accounts, coa_causali, coa_iva, coa_entries.
- Auto entries: FV/NV when SDI status consegnata/mancata_consegna (_push_status); FA/NA on passive import (_import_passive), removed on delete; IN/PG/VC/VI/MB from bank reconciliation, removed on annulla. Contropartita: unica or article.conto_ricavo / supplier.conto_costo (LineIn.article_id added).
- Manual entries (balanced, sottoconti only), rigenera, libro giornale (print), mastrini, bilancio di verifica.
- New company/user module "contabilita". Menu: Vendite, Acquisti, Fisco e IVA, Contabilità generale, Tesoreria, Magazzino, Anagrafiche, Impostazioni.
- Tests: backend/tests/test_iteration31_contabilita.py (run with -n 0) 23/23; frontend iteration_31 passed.
- Backlog: per-bank-account ledger accounts; automatic IVA liquidation entry; year-end closing/opening entries.


## 2026-11-09 — Liquidazione IVA contabile + chiusura/apertura esercizio
- Request: "Chiusura e apertura conti: Aggiungi la chiusura di fine anno con apertura automatica dei conti patrimoniali nel nuovo esercizio" + "Liquidazione IVA contabile: Registra in automatico il giroconto della liquidazione IVA periodica da IVA vendite e acquisti a Erario c/IVA". Choices: button per period; closing with preview; closed year locked.
- backend/contabilita_chiusure.py: GET/POST/DELETE /api/contabilita/liquidazioni (LI entry from ledger IVA balances, 1% interest quarterly, overlap check); GET/POST/DELETE /api/contabilita/chiusura/{anno} (6 entries: economici→CE, risultato→10.03.002, attivi/passivi→60.01.002 on 31/12, riapertura 01/01 via 60.01.001; party-level rows). Year lock via companies.coge_chiusi (manual edits, auto registrations, passive delete, bank unreconcile, payment delete blocked).
- Bilancio excludes closing entries and openings already covered by the range. New params roles: interessi_iva, conto_economico, utile_esercizio, sp_chiusura, sp_apertura.
- UI: card on Liquidazione IVA page; page /contabilita/chiusura (nav "Chiusura esercizio").
- Tests: test_iteration32_chiusure.py + test_iteration31 → 44/44 (-n 0); frontend iteration_32 100%.
- Known cosmetic: journal numbering of opening entries follows the next free number of the new year.



## 2026-11-09 — F24 IVA
- Request: "Versamento F24 IVA: Aggiungi accanto a ogni liquidazione a debito un modello F24 con codice tributo già compilato, pronto da stampare". Choices: downloadable PDF; credit compensation allowed.
- backend/f24.py (tributo codes 6001-6012 / 6031-6033 / 6099 with 0101, due dates shifted to Monday, reportlab PDF); GET/POST /api/liquidazione-iva/f24. Frontend F24Dialog on Liquidazione IVA page (button per period with da_versare>0, up to 5 credit rows, bank selection or none).
- Tests: test_iteration33_f24.py 23/23 (+31/32 regression 67/67 with -n 0).
- Open question: Q4 trimestrale (6099) currently without 1% interest — confirm with accountant.

## 2026-11-09 — Scadenzario fiscale F24
- Request: "Scadenzario fiscale: Mostra in dashboard le prossime scadenze F24 con l'importo, avvisando qualche giorno prima di ogni data". Choices: IVA periodica + ritenute d'acconto (1040); only in-app alert; 5 days before; periodicità IVA per company (default mensile).
- Backend: Company.periodicita_iva; GET /api/scadenze-fiscali (IVA from liquidation, ritenute from passive payments; stati scaduta/in_scadenza/prossima/versato; provvisorio flag); POST/DELETE /api/scadenze-fiscali/versato (blocked while provvisorio); GET /api/scadenze-fiscali/{key}/f24 (PDF ritenute). Collection f24_versamenti.
- Frontend: ScadenzeFiscaliPanel on dashboard, FiscalBanner (red, top of every page, dismiss per day, refresh on versato), Settings "Liquidazione IVA" select, Liquidazione IVA defaults to company periodicity.
- Tests: test_iteration34_scadenze_fiscali.py 15/15 (59/59 with regressions).


## 2026-11-09 — Ricerca diretta conti / clienti / fornitori
- Request: "Nell estratto conto dammi la possibilità di ricercare il conto e cercare clienti e fornitori con ricerca diretta". Choices: both Mastrini and Scadenzario/estratto conto PDF; single search box.
- New frontend/src/components/SearchPicker.jsx (type-ahead, grouped results, keyboard navigation). Mastrini: one search for accounts + clients + suppliers (party sets conto clienti/fornitori from parametri + party filter). Scadenzario clienti/fornitori: search by name/P.IVA/CF over all parties of the type → estratto conto PDF / sollecito.
- Tests: iteration_35 frontend 100%; low UX fixes applied afterwards (reset text on close, scroll highlight, full width mobile, all parties listed).


## 2026-11-09 — Menu parametrizzabili + scheda da anagrafica
- Request: "Tutti i menu e le scelte devono essere parametrozzabili ovvero acceso lo vedo spento non vedo il menu" + "Scheda da anagrafica". Choices: per company and per user; hide item AND block page/API.
- backend/menu_voci.py (catalog 25 items, menu_for path→item, menu_off); tenant() returns 403 for off items; PUT /api/companies/{cid}/menu, /api/users/{uid}/menu, GET /api/menu-voci. Frontend MenuDialog (Companies/Users), Layout filter + route guard, dashboard panels hidden. Parties row + PartyDialog "Scheda contabile" → /contabilita/mastrini?party=ID.
- Tests iteration_36: 36/36 + 82 regression. Known: archivio attive/passive lists blocked only in UI.

## 2026-11-09 — Comunicazioni ai clienti (cortesia, promemoria, solleciti)
- Request: "Crea anche un modulo per l invio delle fatture di cortesia via mail e l invio di promemoria di scadenza imminente ai clienti e anche un modulo per la gestione del solleciti di pagamenti". Choices: cortesia automatic on SDI delivery; daily automatic reminders shown in dashboard; 3 automatic dunning levels; editable texts.
- backend/comunicazioni.py: config per company (all auto OFF by default), templates with placeholders, com_log (dedupe keys per rata), daily tick inside _sdi_loop (Rome time, hour configurable), manual run, manual cortesia resend. Hook in _push_status (consegnata/mancata_consegna). Page /comunicazioni (menu Vendite), dashboard panel.
- Tests iteration_37: 25/25 backend, frontend OK; fixes after: per-rata dunning levels, menu_off respected, manual run label. Real SMTP not available in preview (errors logged).



## 2026-11-09 — IVA indetraibile sulle fatture passive
- Request: "Prevedi anche le registrazioni contabili di fatture passive con Iva iniettabile. Esempio acquisto carburante o telefonia mobile". Choice: % on the supplier, editable on the single invoice.
- Party.detraibilita_iva (default 100) is copied into passive_invoices at import. PUT /api/passive/{id}/detraibilita recreates the accounting entry (blocked when the year is closed). registra_acquisto: the non-deductible VAT (also reverse charge) goes to the cost account. Registro IVA acquisti returns detraibilita_iva/iva_indetraibile/imposta_indetraibile; liquidazione credits only the deductible part. UI: PartyDialog field, DetraibilitaCard in PassiveDetail, note in the Registro acquisti.
- Tests iteration_38: frontend 100%, backend 11/12 → projection fix applied, retest 12/12.
- Backlog: race condition when switching Clienti/Fornitori tabs (LOW).

## 2026-11-09 — Colonna IVA indetraibile
- Request: "Colonna IVA Indetraibile: mostrare la parte di IVA indetraibile per ogni fattura nel registro IVA acquisti e nei report di liquidazione IVA".
- Registro IVA acquisti: new "IVA indetraibile" column per document (amount + detraibile %). Liquidazione IVA: period field iva_indetraibile, column "IVA indetraibile" + annual total; acquisti column renamed "IVA acquisti detraibile (incl. RC)". Both are printable (window.print).
- Verified: test_iteration38 12/12, API check (40% → 62.21 indetraibile, credit 41.47), screenshots of both pages.

## 2026-11-10 — Scadenzario: ricerca e date manuali
- Request: "nella visualizzazione scadenziario clienti e fornitore aggiungi la ricerca del fornitore e le date da inserire a mano . da.. a ..".
- Scadenzario clienti/fornitori: search box moved into the filter bar (finds by registry name, name on the invoice, P.IVA, CF); "Da … a …" fields always visible, typed by hand as gg/mm/aaaa (checked on Enter/exit, invalid dates rejected); choosing a preset period fills the two dates, typing switches to "Periodo personalizzato"; "Azzera" button.
- Verified with screenshots (desktop + mobile) on test data, then the data was removed.

## 2026-11-10 — Saldaconto: partite aperte e chiuse in prima nota
- Request: "in registrazione contabile aggiungi in incasso fattura e pagamento la gestione delle partite aperte e chiuse con la funzione di saldaconto anche automatico". Choices: automatic allocation always from the oldest due date; single archive (updates scadenzario clienti/fornitori); partial amount leaves the partita open for the residual.
- Backend (server.py section "Saldaconto"): GET /api/contabilita/saldaconto/partite, POST /api/contabilita/saldaconto/auto, GET /api/contabilita/saldaconto/registrazione/{rid}. RegIn.saldaconto [{invoice_id, importo, passivo}] validated (party line clienti Avere / fornitori Dare, ≤ residuo, ≤ line amount, date ≥ invoice) → payments/passive_payments with coge_entry_id (metodo contanti if cassa line, else bonifico). Update replaces links (rollback on error), delete removes them (and unlinks bank matches). Payments created from prima nota cannot be deleted from scadenzario.
- Frontend: SaldacontoPanel inside RegistrazioneDialog (per client/supplier line: open partite with amount to match, automatic switch, show closed partite, abbinato/non abbinato).
- Tests iteration_39: backend 12/12 + 54 regression; frontend edit-mode bug fixed by tester; retest 24/24.

## 2026-11-10 — Scheda Incasso/Pagamento
- Request: "quando registro un incasso o un pagamento si deve aprire in automatico una scheda che mi mosterà e le fatture aperte e mi permettera con n click di scegliere e portarle in pagamento. La registrazione di pagamento avviene sempre con una contropartita di banca".
- IncassoSheet.jsx: opens from the Prima nota buttons "Incasso" / "Pagamento", or automatically when causale IN/PG is chosen in a new registration. Search client/supplier → open invoices (oldest due date first) → click to select (residual prefilled, editable/partial, clamped to residual), "Seleziona tutte", bank account (default banca param, any 06.01 sub-account), date. Saves IN = Dare Banca / Avere Clienti, PG = Dare Fornitori / Avere Banca with saldaconto links (scadenzario updated).
- Tests iteration_40: frontend 100%; mobile overflow + amount clamp fixed after test.

## 2026-11-10 — Email di sistema per inviti e reset password
- Request: "nella fase di creazione azienda devi inviare la mail al nuovo utente dell'azienda selezionata non con il suo smtp ma usane uno tuo". Choices: Emergent Managed Email (Resend); company SMTP kept as fallback.
- emailer.send_system_email (POST integrations.emergentagent.com/api/v1/email/send, X-Email-Key=EMERGENT_EMAIL_KEY, from_name=EMAIL_FROM_NAME, safety gate + https-only links). _send_password_link (invite on user creation, admin reset, forgot password) tries system first and falls back to the company SMTP if it fails (e.g. on-prem servers without EMERGENT_EMAIL_KEY or http links).
- Verified: user creation with invite → 202 Accepted from the managed service; test user deleted.

## 2026-11-10 — Email di benvenuto e stato email utenti
- Request: "tutti e due i punti" (welcome email for a company's new users with company name + active modules; invitation delivery status and first sign-in in user management).
- Backend: _send_welcome (system email first, then that company's SMTP as fallback) runs when a user is created with companies or when companies are added in PATCH /users/{id}. _email_event stores last_email + email_log (last 20) on the user for invito/reset/benvenuto (via sistema/smtp, ok/errore). Login sets first_login_at (once) and last_login_at.
- Frontend: Users.jsx new "Email e accessi" column (EmailStato.jsx): last email with outcome and date (full history in the tooltip), first/last sign-in or "Mai entrato".
- Verified: invite + 2 welcome emails 202 Accepted, page screenshot; test data removed. Existing users get first_login_at from their next sign-in.

## 2026-11-10 — HTTPS 443 sul server Windows (Let's Encrypt)
- Request: "sto pubblicando su un mio server va voglio uscire con la porta 443 con un certificato". Choices: Let's Encrypt; domain smartinvoice.digitalmape.it.
- deploy/windows/attiva-https.bat (firewall 80/443, win-acme filesystem validation on C:\nginx\html, PEM in C:\nginx\ssl, nginx-https.conf with 80→301 + 443 TLS1.2/1.3 + HSTS, updates backend .env APP_URL/CORS_ORIGINS https + COOKIE_SECURE true, with backups and rollback), ricarica-web.bat (renewal hook), nginx.conf now serves /.well-known/acme-challenge. Guide INSTALLAZIONE_WINDOWS.md §8.1.
- Verified: nginx -t on both configs, 301 redirect to https. Real certificate issuance can only happen on the user's server.

## 2026-11-10 — Avviso certificato HTTPS e backup su FTP privato
- Request: "Controllo Certificato: Aggiungi in dashboard un avviso per l'amministratore quando il certificato HTTPS sta per scadere / Backup Fuori Sede: Copia ogni notte il backup anche su una cartella di rete o su un servizio cloud". Choices: private FTP; dashboard warning for the backup too.
- backend/sistema.py + GET /api/sistema/avvisi (admin only, ?refresh): TLS check on APP_URL host (cache 6h; yellow ≤21 days, red ≤7/invalid, yellow if not verifiable), reads BACKUP_STATUS_FILE (red: missing/failed/older than 48h; yellow: FTP copy failed). Frontend SistemaAvvisi.jsx on the dashboard (admin only, "Ricontrolla" button).
- deploy/windows/backup.ps1 (backup.bat calls it): mongodump DB_NAME + .env copy, 30-day retention, FTP/FTPS upload via curl.exe with a temporary netrc (BACKUP_FTP_HOST/PORT/USER/PASSWORD/DIR/TLS), writes stato-backup.json. backend.env.example + guide §10.1/§10.2.
- Verified: alert logic unit checks (expired.badssl.com detected), endpoint on preview (cert 54 days → no alert), dashboard banners rendered with mocked data. PowerShell script not runnable here (no Windows).

## 2026-11-10 — Backup FTP per azienda (sezione in Dati azienda)
- Request: "metti un una sezione a parte la configurazione del ftp sotto i parametri per ogni azienda". Choices: each company sends only its own data to its own FTP; nightly at a time chosen per company.
- backend/ftp_backup.py (export of all collections with company_id + company doc + its users without passwords → gzip JSON; ftplib FTP/FTPS explicit with prot_p, creates folders). server.py: GET/PUT /api/company/ftp-backup (password Fernet-encrypted), POST /test, POST /run (tenant_admin); _ftp_tick in the 60s loop (Europe/Rome, once a day at ftp_backup.ora, atomic claim on ultimo_giorno); failed/old (>48h) runs added to /api/sistema/avvisi.
- Frontend: FtpBackupCard.jsx in Settings (admin only) below SMTP: enable switch, server/port/user/password/folder/time/FTPS, "Prova connessione", "Invia backup ora", last result.
- Verified against a local test FTP server: wrong password → clear error, test OK, run OK (file in nested folder, archive content checked), scheduled run fired at the set time, FTPS on non-TLS server → clear message, server down → red dashboard alert; desktop + mobile screenshots. Test data removed.

## 2026-11-10 — Dominio HTTPS cambiato
- Request: "il dominio cambiato in invoix.digitalmape.it cosa devo fare?". nginx-https.conf, attiva-https.bat and INSTALLAZIONE_WINDOWS.md §8.1/§10.2 now use invoix.digitalmape.it (was smartinvoice.digitalmape.it).
- Let's Encrypt error reported ("Invalid response ... acme-challenge ... 404"): attiva-https.bat now kills stale nginx.exe processes, checks locally that port 80 is served by our Nginx from C:\nginx\html (shows the process holding port 80, e.g. IIS/System, and restores the previous config), then checks via the public name; ricarica-web.bat also kills stale processes. Guide row for the 404 error.
- Fix: local port-80 check failed on Windows PowerShell 5.1 (setting the Host header is not allowed → always error) and the netstat filter missed localized "IN ASCOLTO". Now: plain request to 127.0.0.1, prints the exception, shows the listener via Get-NetTCPConnection, service state, nginx -t and the last lines of error.log.
- Fix 2: the response of an extension-less file is byte[] in PS 5.1 (.Trim failed) → the check now reads RawContentStream; the script variable NGINX was renamed NGXDIR because nginx.exe reads an env var called NGINX as inherited sockets ("invalid socket number").

## 2026-11-10 — Invio fattura di cortesia manuale e massivo
- Request: "aggiungi un pulsante invia fattura di cortesia nel dettaglio fatture e prevendi anche un invio massivo".
- Backend (comunicazioni.py): POST /api/comunicazioni/cortesia/{id} accepts optional {to}; GET /cortesia-inviate (invoice ids with a successful courtesy email); POST /cortesia-massiva {ids ≤50, escludi_inviate} → {inviate, saltate, errori}. Company SMTP, admin/contabile only.
- Frontend: CortesiaDialog.jsx (single: recipient prefilled from the client registry, editable for this send) + CortesiaMassivaDialog (skip already sent, batches of 20 with progress, result summary). InvoiceEditor button "Invia fattura di cortesia" for transmitted invoices; Invoices list checkboxes for transmitted invoices, "Seleziona le trasmesse", "Seleziona quelle senza cortesia", bulk button, green mail icon for invoices already sent; selection pruned on filter change.
- Tests iteration_41: backend 100%, frontend 100%; minor items fixed after (batches, tooltip, selection pruning) and re-checked with a screenshot (3 sent via local SMTP sink).

## 2026-11-10 — Ritenute d'acconto professionisti + assoggettamento fornitore
- Supplier fiscal fields (AssoggettamentoFornitore in PartyDialog: soggetto_ritenuta, tipo, aliquota, causale, cassa) applied to passive invoice accounting. Ritenuta payable proportionally on payments (cumulative rounding, last payment closes the exact amount). GET /api/ritenute/mese, /da-versare, F24 PDF, POST /ritenute/{mese}/versato (no future dates) creates coge entry 13.03.002 / bank. Page /ritenute (printable), dashboard RitenutePanel.
- Tests iteration_42: 19/19 backend after rounding fix; frontend OK.

## 2026-11-10 — Diritti di modifica per utente
- Request: "metti i diritti agli utenti di modificare i dati azienda le tabelle e i dati di banca". Choices: tabelle = tabelle contabili + articoli e magazzino + testi comunicazioni; users without the right do not see the section.
- Backend: user.diritti {dati_azienda, banche, tabelle_contabili, articoli_magazzino, testi_comunicazioni}; defaults non-admin: dati/banche off, tabelle & testi = contabile, articoli on; admin all. PUT /api/users/{id}/diritti; /auth/me and /users return computed diritti. tenant() blocks writes on contabilita tables and articles/magazzino; PUT /company merges only the allowed parts; comunicazioni config keeps testi without the right.
- Frontend: DirittiDialog in Gestione utenti ("Diritti: n su 5"); sidebar/route guard hide Dati azienda, Piano dei conti, Articoli, Magazzino; Settings shows only allowed cards; Comunicazioni hides testi.
- Tests iteration_42: backend 18/19 → fixed, 19/19; frontend all rules OK.
- Pending proposal to user: conservazione digitale a norma 10 anni (AdE gratuita / conservatore accreditato / archivio interno) — waiting for choice.

## 2026-11-11 — Importazione di massa da Excel
- Request: "Prevedi sulla base del database la creazione di un foglio Excel prefornattato dove inserire i dati di clienti fornitori articoli listini giacenze di magazzino e saldi di apertura e crea un nuovo meno con le impostazioni di massa. Il file Excel una volta popolato a mano deve essere caricato e alimentare il database". Choices: update existing records; opening balances = accounting balances + open items; preview with errors then confirm.
- backend/importazione.py (/api/importazione, admin): modello (prefilled xlsx, 7 sheets + instructions), anteprima (validation, batch in import_batches), conferma (parties/articles upsert, listini, stock carico "Inventario iniziale", entry AP origine apertura, partite_aperte), storico. partite_aperte merged into scadenzario clienti/fornitori and payable/collectable.
- Frontend: Impostazioni → Importazione di massa (/importazione).
- Tests iteration_47: functional OK; fixed: chart of accounts seeded at preview (conto validation always), payments list on imported partite, UI plurals. Known minor: scadenzario link of an imported partita opens a non-existent invoice page.

## 2026-11-11 — Firma DDT su tablet
- Request: "Ritiro DDT con Firma: Fai firmare il DDT al cliente sul tablet alla consegna e allega la firma al PDF". Choices: destinatario, conducente and vettore sign; both from the app (company user) and via a 24h signing link without login.
- backend/ddt.py: POST /api/ddt/{id}/firme (PNG data URL, one signature per role, confirmed/fatturato only), DELETE /api/ddt/{id}/firme/{ruolo} (admin/contabile, kept in firme_eliminate), POST /api/ddt/{id}/link-firma (token hash, 24h, new link replaces the old one), public /api/public/ddt-firma/{token} GET (no prices, no images) / POST; PDF embeds the signatures with name and Europe/Rome time. tzdata in requirements (Windows).
- Frontend: SignaturePad (canvas pointer events), FirmeDdt card in DdtEditor, public page /firma-ddt/:token.
- Tests iteration_46: 53/53 backend (with t44/t45) + UI; fixed after: deletion audit/status check, firma_link hidden, error shown inside the dialog, canvas resize.

## 2026-11-11 — Prezzi abituali, sconti in cascata, Fattura subito e accompagnatoria
- Request: "Prezzi per Cliente: Proponi in automatico sul DDT il prezzo e lo sconto abituali di ogni cliente per ciascun articolo" + "DDT da Fattura Immediata: pulsante Fattura subito". Choices: listino cliente, then last sale; discount % on the line + cascade (10+5); both immediate invoice from a confirmed DDT and accompanying invoice instead of the DDT.
- Line field `sconto` (invoices and DDT): normalized, totals via fatturapa.line_total, XML ScontoMaggiorazione SC, shown in PDF/print/courtesy. Party `listino` [{article_id, prezzo, sconto}] (ListinoCliente in PartyDialog for clients). GET /api/parties/{pid}/prezzo (listino → ultima_vendita → articolo); DDT editor proposes the price when an article is added and offers to refresh prices when the client changes.
- POST /api/ddt/{id}/fattura (TD01 dated today, Vendita only, DatiDDT) and /api/ddt/{id}/accompagnatoria (from a draft: TD01 dated as the DDT, trasporto → XML DatiTrasporto, stock unload, DDT fatturato/accompagnatoria with no number); deleting the invoice restores the DDT and the stock.
- Tests iteration_45: 25/27 → fixed (riferimento label/date, causale check), 41/41 with iteration44 regression; mobile layout of the line row fixed.

## 2026-11-11 — Grafica fatture e note di credito (solo amministratori)
- Request: "Crea la possibilità solo per gli amministratori di modificare i ficcati dei dati delle fatture e delle note di credito inserendo logo della azienda e altri dati sia da database che descrittivi". Choices: logo top-left, extra company data (telefono, email, PEC, sito, REA, capitale sociale), free footer, main colour, toggle database fields on the document; applies to print and courtesy PDF; separate footer for credit notes.
- GET /api/company/layout (tenant), PUT (tenant_admin only; logo data:image png/jpeg, colour #rrggbb, campi toggles: cliente_codice_fiscale, cliente_codice_destinatario, cliente_pec, cliente_email, cliente_telefono, causale, note_righe, riepilogo_iva, scadenza, coordinate_bancarie). Stored in company.layout.
- Frontend LayoutDocumentiCard in Impostazioni (admin only); InvoicePrint and export_comm.courtesy_pdf use the layout (piede_nc for TD04).
- Tests iteration_48: 18/19 backend → fixed the default campi; frontend OK. Iteration 47 import regression 12/12 (invalid account codes on an unseeded chart are now rejected).

## 2026-11-12 — Riquadri personalizzabili
- Request: "Riquadri personalizzabili: Lasciare che ogni utente possa scegliere quali riquadri vedere e in che ordine, trascinandoli."
- GET/PUT /api/me/riquadri (users.riquadri_pref {ordine, nascosti}, per user); RiquadriSezioni edit mode with @dnd-kit drag (mouse, touch long-press, keyboard), eye toggle, Salva/Annulla/Ripristina, sticky action bar.
- Tests iteration_56: 8/8 backend + all UI flows desktop/mobile; cosmetic fixes applied.

## 2026-11-12 — Dashboard con riquadri proattivi
- Request: "Ridisegnare la dashborad con quadrati proattivi di ogni sezione". Choices: key number + suggested action, red/amber when urgent; tiles on top, existing detail panels below.
- GET /api/dashboard/riquadri (per company counts); RiquadriSezioni.jsx with 8 tiles (fatture, passive, incassi, pagamenti, Ri.Ba., DDT, magazzino, contabilità) gated like the sidebar (modules, menu off, role, diritti, allowed path), loading/error state, staggered fade-in.
- Tests iteration_55: 5/5 backend + UI OK; fixed tile gating vs sidebar, DDT link fallback, error state; render verified desktop + mobile.

## 2026-11-11 — Fatture passive: maschera di registrazione, reverse charge/intra, autofatture, prima nota modificabile
- Request: "Devi gestire in fatture passive tutti i casi di iva, reverse charghe o intracee con generazione autofattura da inviare allo sdi. Le fatture passive quando le registri a mano con il pulsante registra devono andare in un editing di modifica mentre se le registro in modo automatico no. I movimenti di prima nota devono essere modificabili". Choices: autofattura proposed at registration, sent manually; the form edits registration data, cost accounts AND the received invoice data; all prima nota entries editable.
- backend/registra_passiva.py: POST /api/passive/{id}/registrazione(/anteprima) (numero, data, riepilogo rows with per-row cost account, detraibilità, RC rate; original snapshot kept; protocol; accounting re-created); RC for N6.x and foreign suppliers; POST /api/passive/{id}/autofattura; autofattura = invoices doc (autofattura true, sezionale AF, TD16-TD19, cedente = supplier, cessionario = company, DatiFattureCollegate, no DatiPagamento), excluded from sales register/liquidation/ledger/sales accounting/courtesy mail; deleting the draft unlinks it.
- contabilita: acquisto_righe (preview, righe_costo, reverse_charge rows, entry date = data_registrazione); PUT registrazioni allowed on automatic entries (flag modificata).
- Reg. veloce acquisto: RC rate + autofattura for foreign/N6. Full nature list N1–N7 incl. N3.3/3.4/3.6 and N6.1–N6.9.
- Frontend: RegistraPassivaDialog (debounced live preview), AutofatturaView in InvoiceEditor, PassiveDetail Registra button, PrimaNota edit on all entries.
- Tests iteration_53 (plafond hint 8/8 + UI) and iteration_54: 22/23 → fixed entry date, unlink, 00426 for autofatture, duplicate check before update, nature list, live preview; 49 tests rerun OK.

## 2026-11-11 — Dichiarazioni d'intento con plafond e Registrazione veloce
- Requests: "gestisci le dichiarazioni di intento clienti con plafond secondo le nuove regole fiscali" (choices: block invoices over plafond; several declarations per client with plafond, residuo and alerts under 10% + dashboard) and "in registrazione contabile di una fattura di vendita o nota di credito cliente o fornitore apri un form diverso dove mi fai inserire il nome della anagrafica, il totale del documento ivato e tu fai tutti calcoli" (choices: several VAT-rate rows; generates accounting, VAT register and due date).
- backend/intenti.py (/api/intenti CRUD, /avvisi): protocollo 17-6 digits, anno, plafond; usage = N3.5 imponibile of non-rejected invoices (TD04 subtracts, on the linked invoice's declaration). Invoice create/update picks the valid declaration and blocks with 422 when exceeded; re-check on send; per-company asyncio lock against races (single uvicorn worker). XML INTENTO uses the chosen declaration.
- backend/reg_veloce.py (/api/reg-veloce): VAT scorporo per row; sales -> invoices status "manuale" (sezionale MAN/MANNC, IVA_STATI in registers, liquidation, ledger, statement; no XML/SDI); purchases -> passive_invoices manuale, registered with protocollo; accounting via registra_vendita/registra_acquisto; manual N3.5 sales consume plafond; delete reverses.
- Frontend: Intenti.jsx (IntentiCard in PartyDialog, IntentiPanel in dashboard), pages/contabilita/RegistrazioneVeloce.jsx, menu Contabilità → Registrazione veloce, STATUS "manuale".
- Tests iteration_52: 26/26 + regressions; fixed race on plafond, NC declaration, blank numero, manual docs badge/XML, mobile overflow; 51 tests rerun serially OK.

## 2026-11-11 — Distinta Ri.Ba. PDF e pannello Ri.Ba. in dashboard
- Request: "Distinta Ri.Ba. PDF: Aggiungi la stampa PDF della distinta Ri.Ba. da consegnare o archiviare insieme al file CBI. Avviso insoluti in dashboard: Mostra in dashboard gli insoluti del mese e le Ri.Ba. in scadenza nei prossimi 10 giorni".
- GET /api/riba/distinte/{id}/pdf (logo/colore from layout, bank data, effetti, total, signature box); PDF button in Distinte.
- GET /api/riba/riepilogo: insoluti of the month, presented effetti due in 10 days (today included), MP12 rate to present within 10 days; RibaPanel in Dashboard (fatture attive + contabilità + menu riba).
- Tests iteration_51: 36/36 serial; fixed effetti due today missing and popup-blocker issue on PDF open.

## 2026-11-11 — Ri.Ba., insoluti, modifica scadenze, fornitori automatici da XML
- Request: "Quando carichi le fatture passive dallo sdi se non presente carica in automatico il fornitore e prelevare tutti i dati dal xml. Apri poi la scheda fornitore per una verifica. Sviluppa anche la presentazione degli effetti riba. Devono alimentare un conto banca sbf e creare un flusso da inviare alla banca secondo gli standard cbi. Crea anche una procedura automatica per la registrazione degli insoluti e la gestione della modifica delle scadenze." Choices: supplier created and its card opened for confirmation; one SBF account per bank; giroconto at each effetto maturity; insoluto reopens the partita, charges expenses, new due date; insoluti entered manually and from CBI esiti file.
- Passive: _supplier takes CF (=P.IVA if missing), telefono, REA, regime fiscale, IBAN from the XML, flags da_verificare; /passive shows a banner and opens PartyDialog "Verifica fornitore" in sequence; saving clears the flag.
- backend/riba.py (/api/riba): da-presentare (MP12 open rate), distinte (create: riba payments close the rate, SBF account 13.01.1xx per bank saved in banca.conto_sbf, entry RB), CBI flow 120-char records IB/14/20/30/40/50/51/70/EF, automatic maturation (entry RS, in the 60s loop), insoluto (entry RI, rata reopened with nuova scadenza in rate_mod, spese partita MP12), esiti CBI upload match, annulla distinta. /api/scadenze/{invoices|passive}/{id} edits due dates in rate_mod (XML unchanged).
- Party: appoggio_banca/abi/cab; Banca: sia, conto_sbf. Frontend: pages/Riba.jsx, components/RibaDistinte.jsx, ScadenzeDialog (Scadenzario button), menu Vendite → Effetti Ri.Ba.
- CF mandatory for Italian clients/suppliers (also Excel import); live preview of the document layout in Impostazioni; foreign P.IVA accepted.
- Tests iteration_49 (all pass) and iteration_50: 24/25 → fixed rata identity after insoluto (now keyed by scadenza, new date must follow other presented rate); 25/25 serially. Esiti parser validated only against files in our own CBI layout.

## 2026-11-11 — Grafica dei DDT
- Request: "Grafica dei DDT: Apply the same logo, colour and footer to the DDT print and its PDF".
- ddt.ddt_pdf uses company.layout: logo top-left, colour on the title, header box and row table, extra company data in Mittente, new footer field piede_ddt (LayoutIn + textarea in LayoutDocumentiCard).
- Verified: PDF rendered with logo, colour and footer; PDF without layout still generated; frontend compiles.

## 2026-11-11 — Importazione massiva da Excel
- Template Excel, upload, preview with errors, confirmation: clients, suppliers, articles, client price lists, opening stock, opening balances (AP entry) and open items. Existing records are updated.

## 2026-11-11 — DDT e fatturazione differita
- Request: "Gestisci con un nuovo modulo i dati di vendita generando dei ddt Gli articoli dovranno alimentare i movimenti di magazzino in scarico. Prevedi anche io modulo di fatturazione riepilogativa". Choices: stock unload at DDT confirmation (reversed on cancellation); one deferred invoice per client over a period; DDT with causale, porto, vettore, colli, peso, aspetto, other destination, optional prices; insufficient stock = company parameter (avviso / blocca).
- backend/ddt.py (/api/ddt): CRUD drafts, conferma (number n/anno, stock scarico moves with ddt_id, carenze 409 avviso+forza / 400 blocca), annulla (moves removed), PDF (reportlab), fatturazione GET groups / POST creates TD24 invoices with notes "Rif. DDT n. …", ddt_rif → XML DatiDDT (line refs recomputed from the notes), atomic DDT claim against duplicates. Deleting the invoice brings the DDTs back to confermato. Company.ddt_giacenza. Menu Vendite: ddt, fatturazione-differita.
- Frontend: pages Ddt, DdtEditor, FatturazioneDifferita; DdtTrasporto, CarenzeDialog; Settings select; TD24 in the document types.
- Tests iteration_44: 14/14 backend + UI; fixed after: race on generation (checked with 3 parallel calls → 1 invoice), missing article guard, layout of the Trasporto card and mobile.

## 2026-11-10 — Conservazione documenti (archivio decennale + A-Cube)
- Request: "cosa mi proponi per l'achiviazione obbligatoria per anni 10 dei documenti di acquisto e di vendita?". Choices: accredited preservation provider A-Cube (Preservation API) + internal archive; archive includes issued/received invoices with SDI receipts, annual registro IVA vendite/acquisti, libro giornale, registro corrispettivi (PDF) and F24; sending to the provider only manual.
- backend/conservazione.py (/api/conservazione): candidati, archivia (immutable cons_docs: content, sha256, attachments ricevute_sdi.json / dati_ricezione_sdi.json, conserva_fino anno+10; no delete; annual registers only for closed years), file/attachment download, verifica integrity, config per company (own A-Cube credentials encrypted or reuse the SDI A-Cube ones; sandbox/production), test (registers the legal entity), invia (multipart upload + metadata /send per slug fatture, registro-iva-vendite, registro-iva-acquisti, libro-giornale; corrispettivi and F24 internal only), aggiorna (status + receipt PDF), ricevuta. Companies with documents still to keep cannot be deleted.
- Frontend: page /conservazione (Fisco e IVA → Conservazione documenti), menu item parametrizzabile, ConsArchivio / ConsConfigDialog.
- Tests iteration_43: backend 29/29 (A-Cube MOCKED on a local server; real A-Cube not tried, no credentials), frontend OK; fixes after: race on tab switch, .p7m name, verifica on corrupted data, company deletion guard.

## 2026-11-10 — Conferma di lettura fatture di cortesia
- Request: "Conferma di Lettura: Mostra nell'elenco fatture quando il cliente ha aperto l'email di cortesia".
- comunicazioni.py: each courtesy email gets a 1x1 tracking image (APP_URL/api/comunicazioni/t/<token>.gif, only when APP_URL is https); public pixel endpoint records aperta_il (first), aperture, ultima_apertura on com_log. GET /cortesia-inviate now returns {invoice_id: {inviata_il, to, tracciata, aperta_il, aperture}}.
- Invoices.jsx: blue badge "Letta dd/mm hh:mm" (tooltip: recipient, sent date, number of opens) or green mail icon when sent but not yet opened.
- Verified: bulk send via local SMTP sink → tracking image present in the email, pixel hit → "Letta" badge in the list (screenshot). Test data removed.


## 2026-11-12 — Riquadri dashboard personalizzabili
- GET/PUT /api/me/riquadri (per user: visible tiles + order, max 30, ids ≤40 chars); RiquadriSezioni edit mode with @dnd-kit drag and drop, show/hide, reset. Tests iteration_56 OK.

## 2026-11-12 — Pagamenti fornitori + flusso CBI bonifici
- Request: "Genera una procedura per i pagamenti a fornitori che mi mostri le scadenze da data a data con una selezione prendo le partite da pagare gli assegno la banca scegliendo fra le banche aziendali e in automatico registro il pagamento in prima nota chiudo la partita e aggiorno lo scadenzario. Genero anche un file standard cbi da inviare alla banca".
- backend/pagamenti_fornitori.py (/api/pagamenti-fornitori): scadenze dal/al (passive + partite aperte fornitore, IBAN from party or XML), POST distinte (validations: company bank, residuo, rate order, date, supplier IBAN; per-company lock), passive_payments bonifico with distinta_pag_id + coge_entry_id, prima nota PG (Dare fornitori per supplier / Avere bank: default bank → parametro banca, others auto 06.01.1xx saved in banche[].conto_coge), CBI XML CBIPaymentRequest.00.04.00 (needs bank CUC, one bonifico per supplier), annulla (reopens partite). Editing the PG entry in prima nota keeps links and recalculates the distinta (badge "modificata"); edit without links blocked.
- Banca.cuc, PartyIn.iban (PartyDialog, fornitori), menu Acquisti → Pagamenti fornitori (menu id pagamenti-fornitori), origine "pagamenti" in prima nota. Saldaconto now supports partite_aperte and aggregates links per invoice.
- Tests iteration_57/58: backend 36/36, frontend flows OK.
- Backlog: DB-level lock if multiple workers; bank change in edited PG entry not reflected in distinta; mobile card layout for Distinte.

## 2026-11-12 — Avviso pagamenti in dashboard + PDF distinta bonifici
- GET /api/pagamenti-fornitori/riepilogo (window today..+10, Europe/Rome; overdue count/total; manca_iban). Dashboard PagamentiPanel with "Prepara pagamento" (admin/contabile) → /pagamenti-fornitori?dal&al&prepara=1 preselects the window rows that have an IBAN (warning toast for those without).
- GET /api/pagamenti-fornitori/distinte/{id}/pdf (reportlab, company logo/colour: ordering bank, disposizioni, invoice detail, signature box); PDF button in Distinte tab.
- Tests iteration_59: backend 44/44, UI OK; after it: IBAN-less rows skipped on preselect, mobile wrap, singular text, Rome timezone.

## 2026-11-12 — Bollo virtuale + report bolli + Bilancio cliccabile
- Request: "nelle fatture esenti considera il bollo virtuale di 2 euro e aggiungi in anagrafica cliente se il bollo deve essere addebitato al cliente o no. Crea anche un report dove posso vedere il totale degli importi dei bolli da pagare diviso per mese". Choices: auto above 77,47 € of N2.1/N2.2/N3.5/N3.6/N4 amounts (override auto/si/no per invoice); charged clients get a 2 € N1 line (booked on 30.14.002); report counts invoices, NC and autofatture.
- server.py _apply_bollo (InvoiceIn.bollo, LineIn.bollo, PartyIn.bollo_addebito), fields bollo_virtuale/importo/addebitato/esenti/dovuto; XML DatiBollo; courtesy PDF + print note; GET /api/bolli?anno (months, quarters F24 2521-2524 with deadlines, documents; drafts/rejected excluded); page /bolli-virtuali (menu Fisco e IVA, menu id bolli-virtuali); BolloCard in editor.
- Request: "rendi il bilancio proattivo in ogni riga di conto cliccabile visualizzando l'estratto conto della riga di riferimento e nella riga dell estratto conto rendila modificabile". Bilancio rows open SchedaConto sheet (mastrino for the period); rows open RegistrazioneDialog (admin/contabile) via new GET /api/contabilita/registrazioni/{rid}; bilancio refreshes after save.
- Tests iteration_60: backend 17/17, frontend OK; then fixed NC-from-invoice copying bollo line, safer bollo line filter, bollo booked to 30.14.002 (17/17 rerun).

## 2026-11-12 — F24 bolli trimestrale
- GET /api/bolli/f24?anno&trimestre → F24 PDF (f24.build_pdf with optional debito.nota): codice 2521-2524, anno, quarter amount from report, default bank, deadline on next working day (also shown on report cards); "Prepara F24" button per quarter on /bolli-virtuali. Tests iteration_61: 9/9 + regressions OK.

## 2026-11-12 — Bollo versato, avviso bolli in dashboard, cancellazione registrazioni
- Bolli in scadenze fiscali (key BOL-YYYY-Q, tipo bolli) → dashboard ScadenzeFiscaliPanel/FiscalBanner with "Prepara F24"; versato via /api/scadenze-fiscali/versato (entry origine bolli GE Dare 30.14.002 / Avere banca), report shows "Versato il … · trimestre chiuso" with annulla.
- DELETE prima nota allowed for all origins except: vendita of invoices consegnata/mancata_consegna, acquisto of passive received from SDI (origine sdi/sdi_simulato), riba*; side effects for pagamenti (distinta+payments), ritenute/bolli (f24_versamenti). Tests iteration_62: 17/17 + UI OK.
- Backlog: hide delete button for SDI-locked entries; mobile stacking of dashboard fiscal actions.

## 2026-11-12 — Cestino solo dove serve + Storico versamenti F24
- contabilita._blocchi: list_reg returns eliminabile/motivo_blocco (closed year, riba*, vendita consegnata/mancata_consegna, acquisto from SDI); del_reg uses same rules. Prima nota shows trash only when deletable, otherwise lock icon (tap → toast with reason).
- GET /api/f24-storico?anno&tipo (menu storico-f24, page /storico-f24): all f24_versamenti with tipo/periodo/codice/importo/data/prima nota ref, totals per tipo, reprint (IVA via F24Dialog, ritenute /scadenze-fiscali/{key}/f24 now works for any past month, bolli /bolli/f24). Year filter = payment date.
- Tests iteration_63 (ritenute reprint bug fixed afterwards).

## 2026-11-13 — Guida all'uso (manuale operatori)
- Request: "Prepara un manuale di istruzioni per l uso". Choices: in-app Guida page, operators only.
- lib/guida.js (11 chapters: primi passi, dashboard, clienti/fornitori, articoli, fatture, note di credito, DDT, fatture ricevute, scadenzari/comunicazioni, magazzino/corrispettivi, FAQ), pages/Guida.jsx (/guida: index, accent-insensitive search, "Scarica PDF" via print), sidebar button "Guida all'uso" for all roles. Tests iteration_64 OK; fixed drawer close on mobile, index numbering during search, cortesia text (admin/contabile only).
- Keep guida.js updated when operator-facing features change.

## 2026-11-13 — Aiuto in ogni pagina
- components/HelpButton.jsx: floating "?" (bottom-right, all layout pages except /guida, hidden in print) opens a side sheet with the chapter mapped from the route (TD04 → note di credito, unmapped → primi passi) and link to /guida#id (Guida scrolls to hash). Page bottom padding on mobile to avoid overlap. Tests iteration_65: 19/19 mappings OK.

## 2026-11-13 — Guida contabilità (solo contabili)
- User: "Solo per il modulo contabili". 5 chapters with ruolo "contabile" (prima nota, registrazione veloce, schede/bilancio, chiusura, piano dei conti) visible only to admin/contabile (capitoliPer in Guida.jsx); "?" maps /contabilita/* pages to them, operators fall back to Primi passi. Tests iteration_66: 100% functional.

## 2026-11-13 — Invio massivo SDI
- Request: "Prepara un modulo per l invio massivo delle fatture attive allo sdi ... selezionare da data a data e visualizzo solo le fatture da inviare poi posso scegliere tutte con pulsante o una per una con un click. Dopo invio allo sdi".
- GET /api/invio-sdi/da-inviare (bozza/scartata in range), POST /api/invio-sdi {ids} reuses send_sdi per document in date/number order with per-document results; page /invio-sdi (Vendite, admin/contabile, menu id invio-sdi). NC residual check at send now counts only sent credit notes (not drafts). Tests iteration_67: backend 13/13, UI OK.
- PENDING: D-Mape AI assistant (questions asked, user did not answer yet: model, data access, advise-only, placement).
- 2026-11-13: A-Cube login now uses the environment-specific URL (sandbox common-sandbox.api.acubeapi.com, production common.api.acubeapi.com); before, sandbox logins went to production auth. User guided on A-Cube setup (account, Business Registry Configuration for the company VAT, codice destinatario in Fatture e Corrispettivi).
- 2026-11-13 bug fix: invoice print page and courtesy PDF now list all installments (rate) in a table (Rata n/N, scadenza, importo); single due date unchanged; respects layout option "scadenza". Tests iteration_68: 100%.

## 2026-11-13 — Persona fisica fornitori, codici tributo, pagamento predefinito, Excel
- PartyIn: persona giuridica|fisica (+ nome, cognome, data/comune/provincia nascita; fisica → denominazione "Cognome Nome"), ritenuta_codice_tributo (validated against table, default 1040), pagamento_modalita/rate/giorni/fine_mese (clients and suppliers). UI: components/PartyExtra.jsx, AssoggettamentoFornitore codice tributo select.
- backend/codici_tributo.py: ~60 main F24 Erario codes (ritenute, IVA, bollo, dirette, interessi, sanzioni), GET /api/codici-tributo, page /codici-tributo (menu Fisco e IVA).
- Ritenute grouped by supplier codice tributo: righe per codice, F24 PDF with one Erario row per codice (f24.build_pdf debito.righe).
- Invoice editor: client default modalita; RateCard auto-generates rate (debounced) from client defaults until manual edit.
- Import massivo: Clienti/Fornitori sheets extended (pagamento + persona + ritenuta/cassa columns), export prefill with SI/NO, normalised update path.
- Tests iteration_69/70: backend 48/49 then trimming fix; UI 100%.
- Backlog: snapshot codice tributo on passive invoice; per-codice subtotals on /ritenute page; default payment also for supplier invoices registered by hand.


## 2026-11-13 — Menu, banche fornitore, liquidazione IVA PDF, prima nota compatta, insoluti in blocco, bilancio contrapposto
- Menu: Scadenzario clienti, Scadenzario fornitori, Effetti Ri.Ba. moved under "Contabilità generale" (Layout NAV with per-item mod; menu_voci.py groups). Group shows even without contabilita module (only scadenzari).
- Supplier banks: PartyIn.banche_fornitore [{nome, iban, predefinita}] (validated, deduped, one default; party.iban mirrors default). UI BancheFornitore (PartyExtra). Pagamenti fornitori: per supplier select of valid banks + "Altro IBAN…" or input when missing/invalid; POST distinte voci.iban; new IBAN saved to anagrafica (iban_salvati). Excel import keeps other/legacy banks. XML-created suppliers store IBAN only if valid (_iban_safe).
- GET /api/liquidazione-iva/pdf?anno&periodicita&periodo (liquidazione_pdf.py): per period riepilogo + per-aliquota detail vendite/corrispettivi/acquisti, annual summary. Buttons on Liquidazione IVA page.
- Prima nota: one summary row per registration with +/- expand, "Espandi tutte"; print shows detail rows.
- Ri.Ba. tab "Insoluti in blocco": GET /api/riba/scaduti, POST /api/riba/insoluti {effetti, data, giorni, spese_banca, spese_cliente} reusing single insoluto; per-effect errors; matura capped to today; date validation.
- Bilancio: view toggle Verifica / Sezioni contrapposte (Stato patrimoniale + Conto economico, utile/perdita a pareggio), two print buttons.
- Tests iteration_71/72 + re-run: 33/33 backend, UI 100%. Note: tests in backend/tests for it71 must run with -n 0 (shared state).
- Backlog: show 'chiusura' accounts note in contrapposte; D-Mape AI assistant still pending user answers.



## 2026-11-13 — Ritenuta d'acconto in registrazione + fix liquidazione IVA
- Bug: /liquidazione-iva blank page (Cell component lost in previous edit) fixed.
- Registrazione veloce: ritenuta_aliquota/ritenuta_imponibile (prefill from supplier anagrafica, auto if omitted); netto/rate = totale - ritenuta; prima nota Avere 13.03.002 ritenute da versare (acquisti) / Dare 05.02.003 ritenute subite (vendite).
- Registra fattura ricevuta dialog: ritenuta % e imponibile editable (null keep, 0 remove), preview + inline errors; PaymentsPanel refreshes after registration.
- Closing: F24 ritenute "versato" posts Dare 13.03.002 / Avere banca (existing) → conto a zero. Tests iteration_73: backend 19/19, UI OK.


## 2026-11-13 — Certificazione compensi
- GET /api/ritenute/certificazione?anno, /pdf?anno&party (certificazione.py): per supplier compensi lordi, imponibile, ritenute operate/versate per month; tab "Certificazione annuale" in /ritenute. Tests iteration_74 100%.

## 2026-11-14 — Ordini clienti/fornitori, BEM, destinazioni, menu richiudibile
- Choices: elenco destinazioni per cliente; disponibilità = giacenza - impegnato + ordinato; evasione parziale con chiusura forzata; gruppi menu richiudibili.
- backend/ordini.py (/api/ordini/{cliente|fornitore} CRUD, /evadi, /chiudi, /riapri; /api/bem list, /bem/{id}/annulla), ordini_core.py (aggiorna_impegni, storna on DDT/BEM annulla). Evasione cliente → DDT confermato (scarico, destinazione copiata); fornitore → BEM con carico al prezzo netto ordine. Articles: impegnato, ordinato, disponibilita.
- PartyIn.destinazioni; DdtTrasporto/OrdineDialog destination select. Magazzino columns impegnato/ordinato/disponibile.
- Layout NavGroup collapsible (localStorage nav_open, active group always open). Menu ids ordini-clienti, ordini-fornitori, bem.
- Tests iteration_75: backend 20/20 (tester fixed Decimal→float and storna $elemMatch), UI 100%. Evasion serialized per company (BEM numbering).
- Backlog: PDF stampa ordine/conferma d'ordine; evasione di più ordini in un DDT; collegare BEM alla fattura passiva.


## 2026-11-14 — Stampa/email ordini e collegamento BEM-fattura
- ordini_pdf.py + GET /api/ordini/{tipo}/{id}/pdf?conferma, GET/POST /email (allegato PDF, email_inviate). UI: stampa ordine, conferma d'ordine (clienti), invio email.
- GET/POST/DELETE /api/passive/{pid}/bem: collega BEM dello stesso fornitore alla fattura ricevuta, confronto quantità/prezzi d'ordine vs fattura (match codice a parola intera o descrizione). Pannello in dettaglio fattura ricevuta; BEM mostra fattura collegata; delete fattura scollega le BEM; BEM collegata non annullabile.
- Tests iteration_76: backend 18/19 (1 test needs a local SMTP debug server), regression 20/20, UI 100%; minor fixes applied after.


## 2026-11-14 — Fattura da BEM e ordine dal sottoscorta
- Articoli: conto_costo. GET /api/passive/{pid}/proposta-bem ripartisce il riepilogo della fattura per conto costo degli articoli delle BEM collegate (proporzionale, resto sull'ultima riga); RegistraPassivaDialog lo applica con banner e "Ripristina". Righe senza conto → contropartita predefinita (contabilita.acquisto_righe); riepilogo salvato riaggregato per aliquota/natura.
- GET /api/magazzino/proposta-ordine: articoli con disponibilità < scorta minima, quantità = max(lotto, minima - disponibilità), prezzo ultimo carico/costo medio, raggruppati per fornitore abituale; pulsante "Ordina sottoscorta" in Magazzino apre OrdineDialog precompilato (prop bozza).
- Tests iteration_77 + re-run 14/15 (only failing check expects 422 vs existing 400 convention for invalid conto), regression it73 19/19.


## 2026-11-14 — Guida: ordini, BEM, sottoscorta
- lib/guida.js: new chapters "ordini" (Ordini clienti e fornitori) and "bem" (Entrate merce e fatture fornitore); "altro" updated (disponibilità, Ordina sottoscorta); DDT and Fatture ricevute cross-references. HelpButton "?" routes /ordini-* → ordini, /bem → bem.


## 2026-11-14 — Ordini in dashboard
- OrdiniPanel (dashboard): ordini clienti da evadere (ordinati per consegna, ritardi in rosso) e ordini fornitori in ritardo sulla consegna prevista (+ nota in arrivo). Riquadri "Ordini clienti"/"Ordini fornitori" con contatori da /api/dashboard/riquadri (ordini_clienti_da_evadere, ordini_clienti_in_ritardo, ordini_fornitori_in_ritardo, ordini_fornitori_aperti). Tests iteration_78 100%.


## 2026-11-14 — Modulo Produzione (stile Panthera)
- backend/produzione.py (/api/produzione): centri di lavoro (costo orario), distinte base multilivello con ciclo di lavoro (fasi: centro, setup min/lotto, min/pz; controllo cicli; prodotto con gestione magazzino), costo standard roll-up materiali+lavorazioni; ordini di produzione OP n/anno (pianificato→lanciato→in_corso→completato/chiuso), versamento con scarico componenti e carico prodotto a costo materiali+lavorazioni (setup solo primo versamento), 409 carenze/forza, annullo versamento; da ordine cliente (/da-ordine/{oid}, quantità mancante); MRP per low-level code (produrre/acquistare) e genera OP.
- ordini_core.aggiorna_impegni include OP aperti (prodotto → ordinato, componenti → impegnato). Articoli in distinta non eliminabili.
- Frontend: gruppo menu Produzione (/produzione, /produzione/distinte, /produzione/centri, /produzione/mrp), pulsante "Produci" sugli ordini clienti. Menu ids produzione, distinte-base, centri-lavoro, mrp (GET distinte/centri senza vincolo voce).
- Tests iteration_79: backend 12/12, UI 100%; minor fixes applied and re-run 12/12.
- Backlog: guida per la produzione; stampa ordine di produzione / scheda di lavoro; dichiarazione tempi effettivi per fase.


## 2026-11-15 — Produzione: scheda di lavoro PDF e tempi effettivi
- GET /api/produzione/ordini/{oid}/pdf (produzione_pdf.py): scheda di lavoro con componenti da prelevare (per i pezzi ancora da produrre, giacenza, casella prelevato) e fasi (attrezzaggio, min/pz, previsti, effettivi, firma operatore).
- POST/DELETE /api/produzione/ordini/{oid}/fasi/{idx}/tempi[/{tid}]: registrazioni minuti effettivi per fase (sommate in minuti_effettivi), non su ordini pianificati. Ogni ordine ha `consuntivo` (materiali/lavorazioni standard vs effettivi, scostamento €/%, fasi senza tempi).
- UI: pulsanti stampa e "Tempi effettivi" (TempiFasi.jsx) e confronto nel dettaglio ordine. Tests iteration_80: 8/8 + regressione 12/12.

## 2026-11-15 — Ratei e risconti
- User request: "Crea un modulo per la registrazione dei ratei e risconti. Le date di competenza devono essere inserite manualmente in fase di registrazione della fattura. In base al fornitore che dovrà avere un flag di rateo o risconti li farai scegliere in fase di registrazione se esiste o no il rateo e le eventuali date. Crea poi in archivio rateo e risconti con possibilità di modifica veloce e la loro contabilizzazione in simulazione o definitiva. Anche il bilancio potrà avere la scelta di leggere solo registrazioni definitive o anche provvisorio". Scelte: quota a giorni effettivi; tipo proposto dal programma e confermato; storno automatico all'1/1; fornitori e clienti.
- Flag anagrafica `ratei_risconti` (clienti e fornitori). RateoBox in Registrazione veloce e in Registra fattura ricevuta (competenza dal/al, tipo proposto: risconto se competenza oltre il 31/12 dell'anno di registrazione, rateo se inizia prima del 1/1).
- backend/ratei.py (/api/contabilita/ratei): archivio (righe = conti costo/ricavo della registrazione), proposta, inserimento manuale, modifica veloce, elimina, contabilizza {anno, definitiva, ids} → scrittura RR al 31/12 + storno 1/1 (origine "ratei", `provvisoria` in simulazione), annulla. Conti in parametri: ratei_attivi 07.01.001, risconti_attivi 07.01.002, ratei_passivi 14.01.001, risconti_passivi 14.01.002.
- Blocchi: definitivi non modificabili/eliminabili; documento con rateo definitivo non de-registrabile/eliminabile; prima nota non modifica/elimina scritture ratei; chiusura esercizio bloccata con scritture provvisorie. Bilancio e scheda conto: `solo_definitive`, conteggio provvisorie; prima nota badge PROVVISORIA.
- Tests iteration_81: 24/25 → fix (de-registrazione passiva rimuove il rateo, tipo incoerente con le date → 422, importo 0 → 422, rateo spento in ri-registrazione rimosso, matita nascosta in prima nota) → 25/25.
- Backlog: capitolo Guida su ratei/risconti e produzione; rateo/risconto anche per fatture emesse dall'editor (oggi via inserimento manuale in archivio); nota: in preview non ci sono aziende (dati di prova rimossi).



## 2026-11-15 — Guida produzione/ratei + competenza nelle fatture emesse
- lib/guida.js: capitoli "produzione" (distinte, ordini, scheda di lavoro, tempi effettivi e costo effettivo, MRP) e "coge-ratei" (ruolo contabile). HelpButton: /produzione → produzione, /contabilita/ratei-risconti → coge-ratei.
- InvoiceEditor: RateoBox per clienti con flag ratei_risconti; InvoiceIn.rateo salvato in bozza (valida tipo/date vs data fattura, 422). Alla consegna SDI (_push_status) nasce il record ratei_risconti (origine vendita) se il cliente ha il flag; note di credito → importo negativo.
- Tests iteration_82: 13/13 + regressione 25/25.

## 2026-11-15 — Stampa prospetto ratei e risconti
- GET /api/contabilita/ratei/pdf?anno= (ratei_pdf.py, A4 orizzontale): righe con quota nell'esercizio (documento, data reg., anagrafica, tipo, competenza, conti, giorni, imponibile, quota, stato), riepilogo per tipo con conto patrimoniale, contabilizzato in definitiva, totali attivi/passivi, avviso se provvisorio, firma. Pulsante "Stampa prospetto" (rr-pdf-btn). Tests iteration_83: 7/7, UI ok.

## 2026-11-15 — Fix: finestra articolo non scorre (produzione)
- Con gestione magazzino + contropartite il dialog superava l'altezza dello schermo e il pulsante Salva non era raggiungibile. Fix globale in components/ui/dialog.jsx: max-h-[92vh] + overflow-y-auto per tutte le finestre; ArticleDialog max-h-[90vh]. Verificato in anteprima a 1366x600. Va ripubblicato per arrivare in produzione.

## 2026-11-15 — Fix: scadenze fatture passive con ritenuta (produzione)
- Causa: XML con DatiRitenuta ma DettaglioPagamento al lordo → netto/rate senza ritenuta; inoltre le scadenze modificate a mano (rate_mod) non venivano ricalcolate quando si applicava la ritenuta.
- Fix: passive.parse_fattura riscala le rate lorde a totale - ritenuta (- IVA split); _ritenuta_upd/_riscala e registra_passiva._applica riscalano anche rate_mod; migrazione all'avvio _fix_netto_ritenute corregge le fatture esistenti senza pagamenti. Tests iteration_84: 17/17. Da ripubblicare.

## 2026-11-15 — Nuovi fornitori dallo SDI: rilevazione automatica + revisione in dashboard
- Richiesta: parametro conto di costo unico, rilevazione persona fisica/giuridica, ritenute automatiche, allarme in dashboard per i nuovi fornitori da revisionare; poi: rilevare IVA, pagamento e gestioni particolari (reverse charge, intra UE). Scelte: entrambi (automatico + revisione); conto unico proposto, modificabile per fornitore.
- passive._anagrafica: persona/nome/cognome; parse_fattura: ritenuta_info, cassa_info. server._auto_fiscale (nuovo fornitore): persona, ritenuta (tipo/aliquota/base/causale/codice tributo 1040/1038), cassa, gestione_iva (intra_ue/extra_ue/reverse_charge/split_payment; paese da IdPaese), natura_default, pagamento (modalità/rate/giorni/fine mese), conto_costo = parametro costi se contropartita "fornitore".
- GET /api/parties/da-verificare/elenco, POST /api/parties/{pid}/revisione (conferma, applica ritenuta e rigenera le scritture delle fatture da registrare). Dashboard FornitoriRevisionePanel; PartyDialog campo gestione IVA; etichette parametri. Tests iteration_85: 16/16 + UI ok; poi fix conteggio aggiornate e paese IdPaese.
- Nota: gestione_iva è informativa (la registrazione rileva già RC/estero dalle nature e dalla nazione).

## 2026-11-15 — IVA intra UE automatica, conferma fornitori in blocco, condomini
- registra_passiva: is_estero usa anche paese_iva; estero se fornitore gestione_iva intra_ue/extra_ue → integrazione IVA e proposta TD17; autofattura con cedente nazione dal paese IVA. Dashboard: "Conferma i completi" (POST /api/parties/da-verificare/conferma, elenco con `mancano`). Tests iteration_86.
- Condomini (scelte: fattura al lordo, ritenuta all'incasso; causale bonifico parlante): cliente `condominio` (P.IVA vuota, CF numerico 11 cifre, persona giuridica) e `sostituto_imposta`; incasso con ritenuta 4% (PagamentoIn.ritenuta_subita → pagamento metodo "ritenuta" collegato con parent_payment_id, cancellazione a cascata); IncassoSheet propone 4% dell'imponibile (riga Dare 05.02.003 ritenute subite). Fattura: `bonus_edilizio` → Causale XML e stampa con testo per bonifico parlante (norma, n./data fattura, CF beneficiario, P.IVA azienda). Tests iteration_87: 11/11 + fix minori.

## 2026-11-15 — Cancellazione dati azienda

## 2026-11-15 — Fix "Registra documenti mancanti" + utenti + barra laterale
- POST /api/contabilita/rigenera ora registra anche le fatture passive "da_registrare" (stato registrata, data = data fattura, protocollo IVA progressivo per anno, reverse charge N6, scrittura rigenerata); esercizi chiusi segnalati. Tests iteration_89: 9/9.
- PATCH /api/users: modifica email (univoca, email_verified false, invalida link reset), nome, ruolo, aziende; proprio account e titolare: solo nome (UserDialog soloNome, aggiorna barra). Barra laterale desktop fissa o a scomparsa (pulsante pin, rail, localStorage nav_pinned). Tests iteration_90: 9/9 + UI ok, fix minori.

## 2026-11-15 — Autofatture in blocco + barra solo icone
- rigenera: fatture ricevute con reverse charge/estero → autofattura TD16/TD17 in bozza (coge.HOOKS da registra_passiva); TD17 saltata con avviso se il fornitore non ha paese estero; conteggio `autofatture`. Barra laterale: modalità solo icone (sidebar-compact-btn, nav_compact). Tests iteration_91: 10/10 + 9/9, UI ok.


- cancellazione.py: GET /api/azienda/backup (admin, JSON gzip di tutti i dati dell'azienda, senza segreti), POST /api/azienda/cancella {modo totale|parziale, anagrafiche, conferma = ragione sociale}. Parziale: movimenti (fatture, passive, incassi/pagamenti, DDT, BEM, ordini, ordini produzione, movimenti magazzino, prima nota, corrispettivi, Ri.Ba., distinte pagamento, F24, ratei, banca, solleciti, archivi/log); articoli con giacenze azzerate; esercizi chiusi riaperti; numerazione riparte da 1; opzionale clienti/fornitori + intenti. Totale: azienda e tutti i dati. UI CancellazioneAziendaCard in Impostazioni (backup automatico prima). Tests iteration_88: 11/12 → fix PUBLIC_COMPANY_PROJ (esclude password FTP/conservazione anche da GET /api/company).







## 2026-11-16 — Pagamenti su banca/carta/cassa con prima nota
- Nuovo parametro contabile "carta" (06.03.001); GET /api/contabilita/conti-pagamento (banche azienda, carte 06.03, cassa + default per metodo).
- Pagamenti fornitori e incassi clienti dalla fattura creano la registrazione in prima nota (origine "pagamento", PG/IN) sul conto scelto; eliminazione pagamento ↔ registrazione collegata; modifica della scrittura bloccata.
- Blocchi: pagamento su fattura passiva non registrata o con data precedente alla registrazione (dialog, distinte, saldaconto); annullo registrazione bloccato se ci sono pagamenti/compensazioni.
- Test: iteration_92/93.


## 2026-11-16 — Estratto conto carte + pagamenti mancanti in prima nota
- Pagina Contabilità → Estratto conto carte (/contabilita/carte): movimenti del mese per conto carta 06.03, totale, addebito in banca (giroconto GC origine "carta").
- Prima nota: pulsante "Registra pagamenti mancanti" (POST /api/contabilita/pagamenti-mancanti), salta compensazioni, Ri.Ba., distinte, movimenti riconciliati, fatture non registrate o pagamenti antecedenti la registrazione.
- Test: iteration_94/95.

## 2026-11-16 — Esitazione effetti Ri.Ba.
- Banche azienda: spese_emissione e spese_insoluto per effetto. Cliente: flag riba_spese_addebito.
- Fattura con Ri.Ba. per cliente col flag: riga automatica "Spese di incasso Ri.Ba." (N1 esente art.15) = spese × n. rate; rate ricalcolate.
- Distinta: oneri bancari emissione (30.07.011) in prima nota sul conto della banca.
- Tab "Esitazione effetti": effetti in scadenza e scaduti, insoluti in blocco; spese insoluto da banca, riaddebito al cliente (partita separata) se flag.
- Test: iteration_95/96.



## 2026-11-16 — Avviso insoluto al cliente
- Email al cliente (email o PEC, SMTP aziendale) con fattura, scadenza originale, data insoluto, importo, spese addebitate, totale, nuova scadenza, IBAN.
- Esitazione effetti: opzione "Invia avviso email al cliente" (in blocco) + elenco insoluti registrati con Invia/Reinvia (POST /api/riba/effetti/{id}/avviso). Test: iteration_97.


## 2026-11-17 — Ricerca nelle tendine + dashboard colorata
- ui/select.jsx: casella "Cerca…" automatica nelle tendine con 5+ voci (accenti/maiuscole ignorati, codice o testo, Invio/freccia giù seleziona la prima, "Nessun risultato").
- ui/nselect.jsx: sostituto dei <select> nativi (29 file, incluso ContoSelect con gruppi ricercabili per mastro).
- Dashboard: riquadri sezione compatti a colori pieni con pill di stato, KPI colorati, pannelli in griglia a 2 colonne con bordo colorato e altezza massima, grafico multicolore. Test: iteration_98.

## 2026-11-17 — Tema scuro dashboard
- Pulsante "Tema scuro / Tema chiaro" (dashboard-theme-toggle) nella dashboard; scelta salvata nel browser (localStorage fe_dash_dark); classe body.dash-dark solo sulla dashboard, override CSS in index.css; grafico con colori scuri. Verificato con screenshot desktop/mobile.


## 2026-11-17 — Tema scuro ovunque + Aruba Fatturazione Elettronica
- Tema scuro globale: lib/theme.js (useTheme, localStorage fe_dash_dark), pulsante in barra laterale (theme-toggle-btn), icona in barra compatta e header mobile, sincronizzato con il pulsante della dashboard; CSS @media screen in index.css (anche dialog, popover, badge); classe .no-dark per anteprima layout e stampa fattura. Test: iteration_99 (difetti corretti dopo).
- Intermediario SDI "aruba" (sdi_providers.py): login OAuth password (demoauth/auth), upload XML base64 senza firma, esiti da out/getByFilename (stati → RC/NS/MC/NE/DT), ricezione passive da in/findByUsername (ultimi 60 giorni) + in/getByFilename. Impostazioni → Collegamento SDI: Username/Password Aruba. Verificato con mock HTTP; credenziali reali non disponibili (API Aruba da attivare dal cliente).


## 2026-11-17 — Registri IVA multipli + Stampe fiscali
- Più registri IVA acquisti/vendite collegati alle causali; il programma propone il registro e l'utente conferma. Una sola voce di menu "Stampe fiscali" (registri IVA + libro giornale), stampa di prova o definitiva, ristampa delle definitive, numerazione anno/pagina progressiva, le definitive bloccano i movimenti; in Parametri azienda l'admin cancella le stampe e riapre i movimenti. Testato (16/16).

## 2026-11-18 — IA fatture passive + Consulente IA + brand Invoix
- ai_agent.py (Gemini 3 Flash, chiave Emergent): POST /api/ai/passive/analizza (blocchi da 10, 5 in parallelo) propone conto di costo, trattamento IVA, confidenza e motivo; le registrazioni usano ai_conto; quelle dubbie hanno ai_dubbia e compaiono in rosso con badge "VERIFICA IA" in Prima nota e nel pannello della dashboard (GET /dubbie, POST /{id}/rivista per segnarle come verificate). Il trattamento IVA suggerito è solo informativo: la registrazione usa natura e paese della fattura.
- Consulente IA: chat in streaming con sessioni salvate per azienda e utente, contesto limitato ai dati dell'anno dell'azienda attiva, note di credito sottratte. Brand "Invoix" (solo scritta). Testato (14/14 backend + UI).


## 2026-11-18 — Crediti IA pagati alla società padre (Stripe)
- ai_crediti.py: flag "società padre" (una sola) in Anagrafica aziende con listino pacchetti (default Base 500/€10, Pro 2000/€35, Studio 10000/€150, modificabili). 100 crediti omaggio a ogni azienda; 1 credito = 1.000 token effettivi; IA ferma a 0 crediti (402). Interruttore IA in Dati azienda: se spenta le fatture seguono le regole già impostate. Banner piccolo in dashboard + Consulente IA con acquisto via Stripe Checkout (sandbox test), conferma via polling /api/payments/status (accredito una sola volta). Testato 18/18 + UI.

## 2026-11-18 — Protezione sicurezza
- Audit di sicurezza: nessuna password/chiave/stringa DB nel codice (solo in backend/.env, escluso da git). Corretto: CORS limitato a origini esatte (niente '*'), header anti-CSRF obbligatorio X-Requested-With: invoix su tutte le scritture /api (eccetto webhook Stripe), documentazione API disattivata, header di sicurezza (nosniff, X-Frame-Options, HSTS, no-store) su API e nginx, aggiornamento server solo admin, niente chiave Stripe di riserva nel codice, MONGO_URL di docker-compose letto da .env, rimossi vecchi script di test con la password admin. Testato 23/23 + regressione UI.
- Da fare sul server: cambiare la password admin (era presente nella cronologia git), impostare CORS_ORIGINS/APP_URL al dominio reale, permessi ristretti su backend/.env, eventuale autenticazione MongoDB.



## 2026-11-18 — Tendine che si chiudevano subito
- Su telefono/tablet la casella "Cerca" delle tendine apriva la tastiera, la pagina si ridimensionava e la tendina si chiudeva. Ora su schermi touch la casella di ricerca non compare (su computer resta). Verificato su desktop e su mobile simulato (scelta mese "Marzo" in Stampe fiscali).

## 2026-11-18 — Menu riorganizzato
- Nuova voce "Scadenze" con Scadenzario clienti e Scadenzario fornitori (tolti da Contabilità generale). "Pagamenti fornitori" spostata da Acquisti a Contabilità generale.

## 2026-11-18 — Contatore crediti IA in dashboard
- Nuovo riquadro "Crediti IA" (rosa) tra i cruscotti: saldo crediti, crediti usati nel mese, stato (in ordine / da fare sotto 20 o IA spenta / urgente a 0), link al Consulente IA. Spostabile/nascondibile con Personalizza. Dati da /api/dashboard/riquadri (ai_crediti, ai_attiva, ai_consumo_mese).



## 2026-11-18 — Errore 502 sul server dell'utente (invoix.digitalmape.it)
- Causa: deploy/requirements.txt (usato da aggiorna.bat sul server Windows) non conteneva stripe ed emergentintegrations, usati dai moduli IA/crediti → il backend non partiva → nginx 502. Aggiunti (con extra-index-url); risoluzione verificata con pip --dry-run in venv pulito. Il backend ora parte anche se queste librerie mancano (IA e pagamenti rispondono 503 con messaggio chiaro). Nota in INSTALLAZIONE_WINDOWS.md.

## 2026-11-18 — Modulo Porto turistico (stile Navis 3)
- porto.py (/api/porto): configurazione stagione alta/bassa + aliquota IVA ormeggi, listino per fasce di lunghezza (giorno/mese alta-bassa, annuale; IVA esclusa), pontili, posti (creazione in serie, fuori servizio), barche con armatore (cliente), contratti annuali/stagionali/mensili con rate (1-12) e prezzo da listino o manuale, fatturazione rate in bozza, transiti con arrivo/partenza e fattura in bozza alla partenza, controlli: barca troppo lunga, posto occupato, stessa barca in due posti, sosta oltre la partenza prevista.
- Viste: Mappa a griglia per pontile (colori libero/contratto/transito/fuori servizio) e Planning a calendario (2 sett.–3 mesi). Menu "Porto turistico" (6 voci, nascondibili per azienda). Testato 35/35 + UI.
- Backlog: cantiere nautico (preventivi/commesse), charter/broker, prenotazione online.


