# Guida all'installazione su server interno

Questa guida installa l'applicazione di fatturazione elettronica su un vostro server (Linux) usando Docker.
Tempo stimato: 30–45 minuti.

L'applicazione è composta da tre parti, che Docker avvia insieme:

| Parte | Cosa fa |
|---|---|
| **frontend** | Le pagine web (React) servite da Nginx sulla porta 80 |
| **backend** | Il server dell'applicazione (FastAPI, Python), raggiungibile solo dall'interno |
| **mongo** | Il database MongoDB, con i dati salvati in un volume persistente |

---

## 1. Requisiti

- Un server Linux (consigliato **Ubuntu 22.04 / 24.04** o Debian 12), anche virtuale
- Almeno **2 CPU, 4 GB di RAM, 20 GB di disco**
- Accesso come utente con permessi `sudo`
- Un nome per il server nella rete aziendale, ad esempio `fatture.intranet.local` (chiedete all'amministratore di rete di aggiungerlo al DNS interno), oppure l'indirizzo IP del server
- I dati del **server di posta (SMTP)** di ogni azienda: server, porta, utente e password
- Accesso a Internet dal server **solo durante l'installazione** (per scaricare Docker e le librerie)

---

## 2. Installare Docker

Collegatevi al server ed eseguite:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Uscite e rientrate nel server (per attivare il gruppo `docker`), poi verificate:

```bash
docker --version
docker compose version
```

Entrambi i comandi devono mostrare un numero di versione.

---

## 3. Scaricare il codice

**Opzione A – da GitHub** (dopo aver usato "Save to GitHub" su Emergent):

```bash
sudo mkdir -p /opt/fatturazione && sudo chown $USER /opt/fatturazione
git clone https://github.com/VOSTRO-ACCOUNT/VOSTRO-REPOSITORY.git /opt/fatturazione
```

**Opzione B – da archivio ZIP**: copiate l'archivio sul server (ad esempio con WinSCP) ed estraetelo in `/opt/fatturazione`.

Al termine dovete avere le cartelle `/opt/fatturazione/backend`, `/opt/fatturazione/frontend` e `/opt/fatturazione/deploy`.

---

## 4. Configurare l'applicazione

```bash
cd /opt/fatturazione/deploy
cp .env.example .env
```

Generate la chiave con cui vengono cifrate le password SMTP:

```bash
docker run --rm python:3.11-slim sh -c "pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
```

Copiate il risultato e aprite il file di configurazione:

```bash
nano .env
```

Compilate i valori:

| Voce | Cosa inserire |
|---|---|
| `APP_URL` | L'indirizzo con cui gli utenti apriranno l'app, **senza barra finale**. Es. `http://fatture.intranet.local` oppure `http://192.168.1.50` |
| `HTTP_PORT` | Porta del server su cui pubblicare l'app (di solito `80`) |
| `DB_NAME` | Nome del database (lasciate `fatturazione`) |
| `CORS_ORIGINS` | Lo stesso valore di `APP_URL` |
| `COOKIE_SECURE` | `false` se usate `http://`; `true` se usate `https://` (vedi punto 9) |
| `ADMIN_EMAIL` | Email dell'amministratore principale |
| `ADMIN_PASSWORD` | Password iniziale dell'amministratore (almeno 8 caratteri) |
| `EMAIL_FROM_NAME` | Nome dell'applicazione mostrato nelle email di invito e recupero password |
| `SMTP_ENCRYPTION_KEY` | La chiave generata sopra. **Conservatela**: se la perdete, andranno reinserite le password SMTP di tutte le aziende |

Salvate con `Ctrl+O`, `Invio`, poi uscite con `Ctrl+X`.

> **Nota sulle password:** non usate il carattere `$` nei valori del file `.env`.

Proteggete il file:

```bash
chmod 600 .env
```

---

## 5. Avviare l'applicazione

```bash
cd /opt/fatturazione/deploy
docker compose up -d --build
```

La prima volta il comando impiega 5–10 minuti. Controllate che tutto sia attivo:

```bash
docker compose ps
```

Le tre righe `mongo`, `backend` e `frontend` devono essere nello stato `running` (o `Up`).

---

## 6. Primo accesso

1. Aprite il browser su `APP_URL` (es. `http://fatture.intranet.local`)
2. Accedete con `ADMIN_EMAIL` e `ADMIN_PASSWORD`
3. Create la prima azienda e inserite i dati (Partita IVA, indirizzo, IBAN…)
4. **Cambiate la password iniziale**: dopo aver configurato l'email (punto 7) usate "Password dimenticata" dalla pagina di accesso

> L'amministratore viene creato solo al primo avvio. Cambiare `ADMIN_PASSWORD` nel file `.env` in seguito **non** modifica la password già esistente.

---

## 7. Configurare l'email di ogni azienda

Ogni azienda invia le proprie email (solleciti di pagamento con estratto conto, inviti agli utenti, recupero password) dal proprio server di posta.

1. Selezionate l'azienda in alto nel menu
2. Andate su **Dati azienda → Email in uscita (SMTP)**
3. Compilate:

| Campo | Esempio |
|---|---|
| Server SMTP | `smtp.miodominio.it` |
| Sicurezza / Porta | STARTTLS – 587, oppure SSL/TLS – 465 |
| Utente | di solito l'indirizzo email completo |
| Password | la password della casella (viene salvata cifrata) |
| Email mittente | `amministrazione@miodominio.it` |
| Nome mittente | vuoto = ragione sociale |
| Rispondi a | facoltativo |

4. Premete **Salva configurazione**, poi **Invia email di prova** a un vostro indirizzo

Impostazioni tipiche dei provider più comuni:

| Provider | Server | Porta / Sicurezza | Note |
|---|---|---|---|
| Microsoft 365 | `smtp.office365.com` | 587 / STARTTLS | Va abilitato "SMTP autenticato" sulla casella |
| Gmail / Google Workspace | `smtp.gmail.com` | 587 / STARTTLS | Serve una "password per le app" |
| Aruba | `smtps.aruba.it` | 465 / SSL | |
| Register.it | `authsmtp.securemail.pro` | 465 / SSL | |
| Server interno (Exchange, Postfix) | nome del server | 25 / Nessuna oppure 587 | Utente vuoto se il server accetta inoltri dalla rete interna |

Per il **recupero password** e gli **inviti** viene usato il server SMTP della prima azienda a cui l'utente è assegnato; se l'utente non ha aziende con SMTP, viene usata la prima azienda configurata.

---

## 8. Utenti

- Gli amministratori creano gli utenti da **Gestione utenti** e assegnano ruolo (Admin, Contabile, Operatore) e aziende; l'utente riceve via email il link per impostare la password
- Chi si registra da solo resta "in attesa" finché un amministratore non lo approva
- Dopo 5 tentativi di accesso errati l'account viene bloccato per 15 minuti

---

## 9. (Consigliato) HTTPS

Se avete un certificato aziendale, mettete davanti all'app il vostro reverse proxy (Nginx, IIS, Traefik, firewall) con HTTPS che inoltri tutto alla porta `HTTP_PORT` del server. Poi nel file `.env`:

```
APP_URL="https://fatture.intranet.local"
CORS_ORIGINS="https://fatture.intranet.local"
COOKIE_SECURE="true"
```

e ricostruite:

```bash
docker compose up -d --build
```

---

## 10. Backup

Backup del database (da programmare ogni notte, ad esempio con `crontab -e`):

```bash
mkdir -p /opt/backup-fatture
cd /opt/fatturazione/deploy
docker compose exec -T mongo mongodump --archive --gzip --db fatturazione > /opt/backup-fatture/fatture-$(date +%F).gz
```

Esempio di riga per `crontab -e` (ogni notte alle 2:00):

```
0 2 * * * cd /opt/fatturazione/deploy && docker compose exec -T mongo mongodump --archive --gzip --db fatturazione > /opt/backup-fatture/fatture-$(date +\%F).gz
```

Ripristino da un backup:

```bash
cd /opt/fatturazione/deploy
docker compose exec -T mongo mongorestore --archive --gzip --drop < /opt/backup-fatture/fatture-AAAA-MM-GG.gz
```

Copiate periodicamente la cartella dei backup e il file `deploy/.env` su un altro disco o NAS.

---

## 11. Aggiornare l'applicazione

```bash
cd /opt/fatturazione
git pull
cd deploy
docker compose up -d --build
```

I dati restano nel volume del database e non vengono toccati dagli aggiornamenti. Fate sempre un backup prima di aggiornare.

---

## 12. Comandi utili e problemi comuni

| Esigenza | Comando |
|---|---|
| Vedere gli errori del server | `docker compose logs -f backend` |
| Riavviare tutto | `docker compose restart` |
| Fermare l'app | `docker compose down` (i dati restano) |
| Spazio occupato | `docker system df` |

| Problema | Soluzione |
|---|---|
| Dopo l'accesso si torna alla pagina di login | Con `http://` impostate `COOKIE_SECURE="false"`; controllate che `APP_URL` e `CORS_ORIGINS` coincidano con l'indirizzo nel browser, poi `docker compose up -d --build` |
| La pagina è bianca o le chiamate danno errore | `APP_URL` è cambiato: va ricostruito il frontend con `docker compose up -d --build` |
| "Il server SMTP ha rifiutato utente o password" | Verificate utente/password; per Microsoft 365 e Gmail vedete le note al punto 7 |
| "Invio email non riuscito: timed out" | Il firewall blocca la porta 587/465 verso l'esterno: chiedete di aprirla al vostro tecnico di rete |
| Errore all'avvio del backend su `SMTP_ENCRYPTION_KEY` | La chiave non è valida: generatela di nuovo con il comando del punto 4 |

---

## 13. Da sapere

- L'invio delle fatture allo **SDI** e la ricezione delle fatture passive e dei **corrispettivi dal cassetto fiscale** sono **simulati**. Per l'uso reale vanno collegati a un intermediario accreditato (servizio a pagamento).
- I dati presenti nell'ambiente Emergent non vengono esportati con il codice: l'installazione interna parte con un database vuoto.
