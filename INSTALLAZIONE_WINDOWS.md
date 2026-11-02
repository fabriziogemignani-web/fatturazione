# Guida all'installazione su server Windows

Questa guida installa l'applicazione direttamente su Windows, senza Docker. I componenti vengono avviati come **servizi di Windows** e ripartono da soli quando il server si riavvia.

Funziona su **Windows Server 2016, 2019, 2022, 2025** e su **Windows 10/11 Pro**.
Tempo stimato: circa 1 ora.

| Componente | Cosa fa | Dove viene installato |
|---|---|---|
| MongoDB | Database | servizio "MongoDB" |
| Python + FastAPI | Server dell'applicazione (porta 8001, solo interna) | servizio "FatturazioneBackend" |
| Nginx | Pagine web e accesso dalla rete (porta 80) | servizio "FatturazioneWeb" |

In tutta la guida si usa la cartella **`C:\fatturazione`**. Se ne scegliete un'altra, cambiatela anche nei file `deploy\windows\*.bat` e `deploy\windows\nginx.conf`.

I comandi vanno eseguiti in **PowerShell come amministratore**: tasto destro sul menu Start → *Windows PowerShell (amministratore)* oppure *Terminale (amministratore)*.

---

## 1. Requisiti

- Almeno **2 CPU, 4 GB di RAM, 20 GB di disco**
- Utente con diritti di **amministratore**
- Accesso a Internet **durante l'installazione** (per scaricare i programmi e le librerie)
- Un nome per il server nella rete, ad esempio `fatture.intranet.local` (da aggiungere al DNS interno), oppure il suo indirizzo IP
- I dati del **server di posta (SMTP)** di ogni azienda

---

## 2. Installare i programmi necessari

Scaricate e installate, in quest'ordine, lasciando le opzioni predefinite salvo dove indicato.

| # | Programma | Dove scaricarlo | Note |
|---|---|---|---|
| 1 | **Git for Windows** | https://git-scm.com/download/win | Opzioni predefinite |
| 2 | **Python 3.11** (64 bit) | https://www.python.org/downloads/windows/ → "Python 3.11.x" → *Windows installer (64-bit)* | Spuntate **"Add python.exe to PATH"** nella prima schermata. Non usate la versione 3.12 o successive |
| 3 | **Node.js 20 LTS** | https://nodejs.org/en/download → versione 20 LTS, *Windows Installer (.msi)* | Opzioni predefinite |
| 4 | **MongoDB Community Server 7** | https://www.mongodb.com/try/download/community → Version 7.0, Platform Windows, Package msi | Scegliete *Complete*, lasciate spuntato **"Install MongoDB as a Service"**. MongoDB Compass è facoltativo |
| 5 | **MongoDB Database Tools** | https://www.mongodb.com/try/download/database-tools → Windows, msi | Servono per i backup |
| 6 | **Nginx per Windows** | https://nginx.org/en/download.html → *Stable version*, file `nginx-1.x.x.zip` | Estraete lo zip e rinominate la cartella in **`C:\nginx`** (deve contenere `C:\nginx\nginx.exe`) |
| 7 | **NSSM** (gestione servizi) | https://nssm.cc/download → `nssm 2.24` | Estraete lo zip e copiate `win64\nssm.exe` in **`C:\Windows\System32`** |

Chiudete e riaprite PowerShell come amministratore, poi verificate:

```powershell
git --version
python --version
node --version
nssm version
```

Ogni comando deve mostrare un numero di versione (Python deve essere **3.11.x**, Node **v20.x**).

Installate infine **yarn**:

```powershell
npm install -g yarn
yarn --version
```

---

## 3. Scaricare il codice da GitHub

```powershell
git clone https://github.com/VOSTRO-UTENTE/NOME-REPOSITORY.git C:\fatturazione
```

L'indirizzo esatto lo trovate su GitHub, pulsante verde **"Code"** → HTTPS.
Se il repository è privato, Windows apre una finestra di accesso a GitHub: accedete con il vostro account (oppure usate come password un *Personal access token*, vedi GitHub → Settings → Developer settings → Personal access tokens).

Verificate:

```powershell
dir C:\fatturazione
```

Dovete vedere `backend`, `frontend`, `deploy`, `INSTALLAZIONE_WINDOWS.md`.

> **Senza accesso a GitHub dal server:** dal vostro PC scaricate da GitHub *Code → Download ZIP*, copiatelo sul server ed estraetelo in `C:\fatturazione`.

---

## 4. Installare il server dell'applicazione (Python)

```powershell
cd C:\fatturazione
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\pip.exe install -r deploy\requirements.txt
```

L'installazione richiede qualche minuto. Al termine non devono comparire righe con `ERROR`.

Generate la chiave che cifra le password SMTP e **copiatela** (vi serve al punto successivo):

```powershell
.\venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 5. Configurare l'applicazione

Copiate il modello di configurazione e apritelo con il Blocco note:

```powershell
copy C:\fatturazione\deploy\windows\backend.env.example C:\fatturazione\backend\.env
notepad C:\fatturazione\backend\.env
```

> Se Windows chiede di sovrascrivere un `.env` già presente, rispondete **Sì**.

Compilate i valori (lasciate le virgolette):

| Voce | Cosa inserire |
|---|---|
| `MONGO_URL` | Lasciate `mongodb://127.0.0.1:27017` |
| `DB_NAME` | Lasciate `fatturazione` |
| `APP_URL` | L'indirizzo con cui gli utenti apriranno l'app, **senza barra finale**: es. `http://fatture.intranet.local` oppure `http://192.168.1.50` |
| `CORS_ORIGINS` | Lo stesso valore di `APP_URL` |
| `COOKIE_SECURE` | `false` con `http://`; `true` solo se usate `https://` |
| `ADMIN_EMAIL` | Email dell'amministratore principale |
| `ADMIN_PASSWORD` | Password iniziale dell'amministratore (almeno 8 caratteri, senza il carattere `$`) |
| `EMAIL_FROM_NAME` | Nome dell'applicazione nelle email di invito e recupero password |
| `SMTP_ENCRYPTION_KEY` | La chiave generata al punto 4. **Conservatela in un posto sicuro** |

Salvate e chiudete il Blocco note.

Controllate che il file si chiami esattamente `.env` (e non `.env.txt`):

```powershell
dir -Force C:\fatturazione\backend\.env
```

Deve comparire una riga con `.env`. Se invece compare un errore "Impossibile trovare il percorso", il file non c'è o ha un altro nome: ripetete il comando `copy` sopra.

Ora la configurazione delle pagine web. Aprite:

```powershell
notepad C:\fatturazione\frontend\.env
```

**Cancellate tutto il contenuto** e scrivete una sola riga, con lo stesso indirizzo di `APP_URL`:

```
REACT_APP_BACKEND_URL=http://fatture.intranet.local
```

Salvate e chiudete.

---

## 6. Preparare le pagine web

```powershell
cd C:\fatturazione\frontend
yarn install --frozen-lockfile
yarn build
```

La prima volta richiede 5–10 minuti. Alla fine deve comparire `Compiled successfully` (eventuali avvisi gialli *warning* sono normali) e deve esistere la cartella `C:\fatturazione\frontend\build`.

---

## 7. Prova manuale del server dell'applicazione

```powershell
C:\fatturazione\deploy\windows\avvia-backend.bat
```

Dovete vedere `Application startup complete`. Lasciate la finestra aperta e da un browser **sul server** aprite:

```
http://127.0.0.1:8001/api/auth/me
```

Deve comparire `{"detail":"Non autenticato"}`: significa che funziona.
Tornate in PowerShell e premete `Ctrl+C` per fermarlo (rispondete `S` se chiede di terminare).

> Se compare un errore, vedete la sezione *Problemi comuni* in fondo.

---

## 8. Installare i servizi di Windows

**Server dell'applicazione:**

```powershell
mkdir C:\fatturazione\logs
nssm install FatturazioneBackend C:\fatturazione\deploy\windows\avvia-backend.bat
nssm set FatturazioneBackend AppDirectory C:\fatturazione\backend
nssm set FatturazioneBackend AppStdout C:\fatturazione\logs\backend.log
nssm set FatturazioneBackend AppStderr C:\fatturazione\logs\backend.log
nssm set FatturazioneBackend DependOnService MongoDB
nssm set FatturazioneBackend Start SERVICE_AUTO_START
nssm start FatturazioneBackend
```

**Server web (Nginx):**

```powershell
copy C:\fatturazione\deploy\windows\nginx.conf C:\nginx\conf\nginx.conf
nssm install FatturazioneWeb C:\nginx\nginx.exe
nssm set FatturazioneWeb AppDirectory C:\nginx
nssm set FatturazioneWeb DependOnService FatturazioneBackend
nssm set FatturazioneWeb Start SERVICE_AUTO_START
nssm start FatturazioneWeb
```

Rispondete **Sì** se Windows chiede di sovrascrivere `nginx.conf`.

**Aprire la porta 80 nel firewall di Windows:**

```powershell
New-NetFirewallRule -DisplayName "Fatturazione Elettronica (HTTP)" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
```

Controllate che i tre servizi siano in esecuzione:

```powershell
Get-Service MongoDB, FatturazioneBackend, FatturazioneWeb
```

Tutti devono essere **Running**.

> **La porta 80 è già usata (ad esempio da IIS)?** In `C:\nginx\conf\nginx.conf` cambiate `listen 80;` in `listen 8080;`, aprite la porta 8080 nel firewall, aggiungete `:8080` ad `APP_URL` e `CORS_ORIGINS` nel file `backend\.env` e a `REACT_APP_BACKEND_URL` nel file `frontend\.env`, poi ripetete il punto 6 e riavviate i servizi (`nssm restart FatturazioneBackend` e `nssm restart FatturazioneWeb`).

---

## 9. Primo accesso

1. Da un PC della rete aprite il browser su `APP_URL` (es. `http://fatture.intranet.local`)
2. Accedete con `ADMIN_EMAIL` e `ADMIN_PASSWORD`
3. Create la prima azienda e completate i dati
4. In **Dati azienda → Email in uscita (SMTP)** configurate il server di posta e usate **Invia email di prova** (impostazioni dei provider più comuni al punto 7 della guida [INSTALLAZIONE.md](INSTALLAZIONE.md))
5. Cambiate la password iniziale con il pulsante **Cambia password** nel menu laterale
6. Create gli altri utenti da **Gestione utenti**

> Cambiare `ADMIN_PASSWORD` nel file `.env` dopo il primo avvio **non** modifica la password già esistente.

---

## 10. Backup automatico ogni notte

Il file `C:\fatturazione\deploy\windows\backup.bat` salva il database e la configurazione in `C:\backup-fatture` e cancella i backup più vecchi di 30 giorni.

Provatelo una volta:

```powershell
C:\fatturazione\deploy\windows\backup.bat
dir C:\backup-fatture
```

Programmatelo ogni notte alle 2:00:

```powershell
schtasks /create /tn "Backup Fatturazione" /tr "C:\fatturazione\deploy\windows\backup.bat" /sc daily /st 02:00 /ru SYSTEM
```

Copiate regolarmente `C:\backup-fatture` su un NAS o un altro disco.

**Ripristino** di un backup (sostituisce i dati attuali):

```powershell
nssm stop FatturazioneBackend
& "C:\Program Files\MongoDB\Tools\100\bin\mongorestore.exe" --gzip --archive=C:\backup-fatture\fatture-AAAA-MM-GG.gz --drop
nssm start FatturazioneBackend
```

> Se il percorso `C:\Program Files\MongoDB\Tools\100\bin` non esiste, cercate `mongodump.exe` in `C:\Program Files\MongoDB\Tools` e correggete il percorso anche dentro `backup.bat`.

---

## 11. Aggiornare l'applicazione

Quando l'applicazione viene modificata e salvata di nuovo su GitHub, sul server eseguite **come amministratore**:

```powershell
C:\fatturazione\deploy\windows\aggiorna.bat
```

Lo script ferma i servizi, scarica le novità (`git pull`), aggiorna le librerie, ricostruisce le pagine web e riavvia tutto. I dati e i file `.env` non vengono toccati. Fate un backup prima di aggiornare.

> Se `git pull` segnala un conflitto sul file `frontend\.env`, eseguite `git checkout -- frontend/.env` in `C:\fatturazione`, rilanciate l'aggiornamento e al termine reinserite la riga `REACT_APP_BACKEND_URL=...` (punto 5) e ripetete il punto 6.

---

## 12. Comandi utili

| Esigenza | Comando |
|---|---|
| Stato dei servizi | `Get-Service MongoDB, FatturazioneBackend, FatturazioneWeb` |
| Riavviare l'applicazione | `nssm restart FatturazioneBackend` |
| Riavviare il server web | `nssm restart FatturazioneWeb` |
| Vedere gli errori | `Get-Content C:\fatturazione\logs\backend.log -Tail 50` |
| Errori del server web | `Get-Content C:\nginx\logs\error.log -Tail 50` |

---

## 13. Problemi comuni

| Problema | Soluzione |
|---|---|
| `python` non viene riconosciuto | Python è stato installato senza "Add to PATH": reinstallatelo spuntando l'opzione, poi riaprite PowerShell |
| Errori durante `pip install` | Verificate di usare Python **3.11** (`python --version`) e ripetete il comando del punto 4 |
| `KeyError: 'SMTP_ENCRYPTION_KEY'` o simile all'avvio | Manca una voce nel file `backend\.env`: controllatelo rispetto al punto 5 |
| `ValueError: Fernet key must be 32 url-safe base64-encoded bytes` | La chiave SMTP non è valida: generatela di nuovo (punto 4) |
| `ServerSelectionTimeoutError` | MongoDB non è avviato: `Start-Service MongoDB` |
| La pagina non si apre dagli altri PC | Controllate la regola del firewall (punto 8) e che il nome del server sia nel DNS; provate con l'indirizzo IP |
| Dopo l'accesso si torna alla pagina di login | Con `http://` serve `COOKIE_SECURE="false"`; `APP_URL`, `CORS_ORIGINS` e `REACT_APP_BACKEND_URL` devono coincidere esattamente con l'indirizzo nel browser. Dopo le modifiche: punto 6 e `nssm restart FatturazioneBackend` |
| Pagina bianca o errori "Network Error" | `REACT_APP_BACKEND_URL` nel file `frontend\.env` è sbagliato: correggetelo e ripetete il punto 6 |
| Il servizio FatturazioneWeb non parte | La porta 80 è occupata: vedete la nota al punto 8 |
| "Invio email non riuscito: timed out" | Il firewall aziendale blocca le porte 587/465 verso l'esterno |

---

## 14. Da sapere

- L'invio delle fatture allo **SDI**, la ricezione delle fatture passive e dei **corrispettivi dal cassetto fiscale** sono **simulati**: per l'uso reale vanno collegati a un intermediario accreditato.
- I dati presenti nell'ambiente Emergent non vengono esportati con il codice: l'installazione sul server parte con un database vuoto.
