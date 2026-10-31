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

## Backlog
- P0: real intermediary (OpenAPI / Aruba / Fatture in Cloud) for send + notifications
- P1: passive cycle (import received XML from fornitori), digital signature/conservazione sostitutiva
- P2: FPA12 for Pubblica Amministrazione, bollo virtuale, ritenuta d'acconto, multi-company
