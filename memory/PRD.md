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

