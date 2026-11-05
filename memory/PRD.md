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

- P1: digital signature/conservazione sostitutiva; detraibilità parziale/pro-rata IVA acquisti; export commercialista
- P2: bollo virtuale; autofatture TD16-TD19 XML
