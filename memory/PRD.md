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
