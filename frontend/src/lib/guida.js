export const CAPITOLI = [
  {
    id: "inizio", titolo: "Primi passi", sezioni: [
      { t: "Accedere al programma", p: ["Apri il programma e inserisci email e password ricevute dall'amministratore, poi premi Accedi.", "Se hai dimenticato la password usa \"Password dimenticata?\" nella pagina di accesso: riceverai un'email con il link per sceglierne una nuova.", "Per cambiare la password in qualsiasi momento usa il pulsante \"Cambia password\" in basso a sinistra, sotto il tuo nome."] },
      { t: "Scegliere l'azienda", p: ["Se lavori per più aziende, in alto nella barra laterale trovi il nome dell'azienda attiva: cliccalo per passare a un'altra.", "Tutto quello che vedi (fatture, clienti, scadenze) riguarda solo l'azienda attiva. Prima di creare un documento controlla sempre di essere nell'azienda giusta."] },
      { t: "Il menu", p: ["Il menu a sinistra è diviso in gruppi (Vendite, Acquisti, Anagrafiche…). Vedi solo le voci che l'amministratore ha abilitato per te: se una funzione descritta qui non compare, chiedi all'amministratore.", "Da telefono il menu si apre con il pulsante con le tre linee in alto a sinistra."] },
      { t: "Il tuo ruolo di operatore", p: ["Come operatore prepari i documenti: clienti, articoli, fatture, note di credito e DDT.", "L'invio delle fatture allo SDI, i pagamenti, la contabilità e le impostazioni sono riservati ad amministratori e contabili. Quando una fattura è pronta, salvala e avvisa chi deve inviarla."] },
    ],
  },
  {
    id: "dashboard", titolo: "Dashboard", sezioni: [
      { t: "I riquadri", p: ["La dashboard si apre dopo l'accesso. I riquadri in alto mostrano, per ogni sezione, un numero chiave e l'azione consigliata (per esempio \"3 bozze da completare\"). Cliccando un riquadro vai direttamente alla pagina giusta.", "Sotto i riquadri trovi i dettagli: andamento del fatturato, scadenze di clienti e fornitori e altri avvisi."] },
      { t: "Personalizzare i riquadri", p: ["Premi \"Personalizza\" sopra i riquadri: puoi nasconderli o mostrarli con l'icona dell'occhio e cambiarne l'ordine trascinandoli (da telefono tieni premuto il riquadro e poi spostalo).", "Premi Salva per confermare o Ripristina per tornare all'ordine iniziale. La scelta vale solo per te."] },
    ],
  },
  {
    id: "anagrafiche", titolo: "Clienti e fornitori", sezioni: [
      { t: "Creare un cliente", p: ["Vai in Anagrafiche → Clienti e fornitori, scegli la scheda Clienti e premi \"Nuovo cliente\".", "Inserisci ragione sociale (o nome e cognome per i privati), indirizzo completo, partita IVA e codice fiscale.", "Il codice fiscale è obbligatorio per i clienti italiani. Per i clienti esteri indica il paese: il codice fiscale non serve."] },
      { t: "Codice destinatario e PEC", p: ["Per far arrivare la fattura elettronica al cliente serve il suo codice destinatario (7 caratteri) oppure la sua PEC. Se il cliente non li ha, lascia 0000000: la fattura arriverà nella sua area riservata dell'Agenzia delle Entrate.", "Per la Pubblica Amministrazione attiva l'opzione Pubblica Amministrazione e inserisci il codice univoco ufficio di 6 caratteri."] },
      { t: "Opzioni utili del cliente", p: ["Modalità di pagamento e banca d'appoggio: vengono proposte in automatico in ogni nuova fattura.", "Split payment: per gli enti pubblici che versano loro l'IVA.", "Addebita il bollo virtuale: se attivo, nelle fatture esenti sopra 77,47 € viene aggiunta la riga del bollo da 2 € a carico del cliente."] },
      { t: "Fornitori", p: ["Nella scheda Fornitori si lavora allo stesso modo. Inserisci anche l'IBAN del fornitore: serve per pagarlo con bonifico.", "I fornitori arrivati con le fatture dallo SDI vengono creati in automatico con i dati dell'XML e segnalati \"da verificare\": aprili, controlla i dati e salva per confermarli."] },
      { t: "Cercare e modificare", p: ["Usa la casella di ricerca in alto nell'elenco per trovare un'anagrafica per nome, partita IVA o codice fiscale. Clicca la riga per aprirla e modificarla."] },
    ],
  },
  {
    id: "articoli", titolo: "Articoli e servizi", sezioni: [
      { t: "Creare un articolo", p: ["In Anagrafiche → Articoli e servizi premi \"Nuovo articolo\": inserisci codice, descrizione, unità di misura, prezzo e aliquota IVA.", "Quando scrivi una riga di fattura o di DDT puoi richiamare l'articolo: descrizione, prezzo e IVA si compilano da soli."] },
      { t: "Listini e sconti", p: ["Se il cliente ha prezzi o sconti particolari, il programma li applica in automatico quando scegli l'articolo per quel cliente. Gli sconti si scrivono anche in cascata, per esempio 10+5."] },
    ],
  },
  {
    id: "fatture", titolo: "Fatture", sezioni: [
      { t: "Creare una fattura", p: ["Vai in Vendite → Fatture emesse e premi \"Nuova fattura\".", "1. Scegli il cliente. Se non esiste ancora, crealo con il pulsante + accanto al campo.", "2. Controlla la data: il numero viene assegnato in automatico secondo il registro di numerazione.", "3. Aggiungi le righe con \"Aggiungi riga\": descrizione (o articolo), quantità, prezzo, eventuale sconto e aliquota IVA.", "4. A destra il riepilogo calcola imponibile, IVA e totale mentre scrivi.", "5. Premi Salva: la fattura resta in bozza finché non viene inviata allo SDI."] },
      { t: "IVA, esenzioni e natura", p: ["Per le righe senza IVA scegli aliquota 0 e la natura corretta (per esempio N2.2 non soggette, N3.5 non imponibili con dichiarazione d'intento, N4 esenti). Se non sei sicuro, chiedi al contabile.", "Se il cliente ha una dichiarazione d'intento, sotto le righe N3.5 compare il residuo disponibile: se lo superi la fattura non si può salvare."] },
      { t: "Bollo virtuale", p: ["Se gli importi esenti o non imponibili superano 77,47 €, il programma applica da solo il bollo virtuale di 2 €. Nel riepilogo il riquadro \"Bollo virtuale\" mostra il calcolo; puoi scegliere \"Applica sempre\" o \"Non applicare\" se serve.", "Se il cliente ha l'addebito del bollo, viene aggiunta la riga da 2 € e il totale aumenta."] },
      { t: "Pagamento e scadenze", p: ["Nella sezione pagamento scegli la modalità (bonifico, Ri.Ba., contanti…) e le scadenze: puoi dividere il totale in più rate con date diverse. La somma delle rate deve essere uguale al netto da pagare."] },
      { t: "Stampa e PDF", p: ["Dopo il salvataggio puoi stampare la fattura o salvarla in PDF con il pulsante della stampante. Il documento usa logo, colori e testi impostati dall'amministratore."] },
      { t: "Invio allo SDI e stati", p: ["L'invio allo SDI lo fa un amministratore o un contabile. Lo stato della fattura si legge nell'elenco:", "Bozza: si può ancora modificare o eliminare.", "Inviata allo SDI: in attesa di esito, non si può modificare.", "Consegnata: recapitata al cliente.", "Mancata consegna: lo SDI l'ha accettata ma non l'ha potuta recapitare; il cliente la trova nella sua area riservata.", "Scartata dallo SDI: c'è un errore. Apri la fattura, correggi quanto indicato nel messaggio di scarto, premi \"Salva correzioni\" e avvisa chi la deve reinviare (entro 5 giorni)."] },
      { t: "Fattura di cortesia", p: ["Su una fattura inviata, amministratori e contabili possono spedire al cliente via email una copia in PDF con il pulsante \"Invia fattura di cortesia\". Se un cliente la chiede, avvisa loro. È solo una copia: quella valida è la fattura elettronica."] },
    ],
  },
  {
    id: "note-credito", titolo: "Note di credito", sezioni: [
      { t: "Stornare una fattura", p: ["Apri la fattura da stornare e premi \"Crea nota di credito\". Puoi stornarla tutta oppure solo alcune righe o una parte degli importi.", "La nota di credito si crea già collegata alla fattura e con le righe copiate: controlla, modifica se serve e salva."] },
      { t: "Nota di credito libera", p: ["Puoi anche creare una nota di credito da zero con il pulsante \"Nuova nota di credito\" nell'elenco delle fatture. Indica sempre la fattura a cui si riferisce."] },
    ],
  },
  {
    id: "ddt", titolo: "Documenti di trasporto (DDT)", sezioni: [
      { t: "Creare un DDT", p: ["Vai in Vendite → Documenti di trasporto e premi \"Nuovo DDT\". Scegli il cliente, la destinazione della merce, la causale (es. Vendita), il trasporto e aggiungi le righe degli articoli.", "Con \"Salva bozza\" puoi riprendere il DDT più tardi; con \"Conferma e scarica\" il DDT diventa definitivo, ottiene il numero e scarica la merce dal magazzino."] },
      { t: "Stampa e firma", p: ["Con Stampa ottieni il PDF del DDT da consegnare al trasportatore. Se previsto, il cliente può firmare la ricevuta di consegna dal link che gli viene inviato."] },
      { t: "Dal DDT alla fattura", p: ["Fattura accompagnatoria: dal DDT di vendita in bozza crea subito una fattura che vale anche come documento di trasporto.", "Fattura subito: da un DDT confermato crea la fattura con le stesse righe.", "Fatturazione differita: in Vendite → Fatturazione differita selezioni i DDT confermati del periodo e premi \"Genera fatture\": viene creata una fattura per cliente con tutti i suoi DDT."] },
    ],
  },
  {
    id: "passive", titolo: "Fatture ricevute", sezioni: [
      { t: "Consultare le fatture dei fornitori", p: ["In Acquisti → Fatture ricevute trovi le fatture arrivate dallo SDI o caricate da file. Puoi cercarle per fornitore, numero o data e aprirle per vedere righe, importi e scadenze.", "Il caricamento dei file XML e la registrazione contabile sono riservati ad amministratori e contabili."] },
      { t: "Fornitori da verificare", p: ["Se in alto compare l'avviso \"fornitori creati in automatico\", apri le schede indicate, controlla i dati presi dall'XML e salva per confermarli."] },
    ],
  },
  {
    id: "scadenze", titolo: "Scadenzari e comunicazioni", sezioni: [
      { t: "Scadenzario clienti e fornitori", p: ["Vendite → Scadenzario clienti mostra le rate da incassare; Acquisti → Scadenzario fornitori quelle da pagare. Le scadenze passate sono evidenziate in rosso.", "Puoi filtrare per cliente o fornitore e per periodo. La registrazione di incassi e pagamenti è riservata ad amministratori e contabili."] },
      { t: "Comunicazioni ai clienti", p: ["In Vendite → Comunicazioni ai clienti trovi i testi delle email inviate ai clienti (fattura di cortesia, promemoria di scadenza e solleciti di pagamento) e lo storico degli invii. Promemoria e solleciti partono in automatico in base alle scadenze aperte."] },
    ],
  },
  {
    id: "altro", titolo: "Magazzino e corrispettivi", sezioni: [
      { t: "Giacenze di magazzino", p: ["In Magazzino → Giacenze e movimenti vedi la quantità disponibile di ogni articolo e i movimenti di carico e scarico. I DDT confermati e le fatture con articoli aggiornano le giacenze da soli."] },
      { t: "Corrispettivi", p: ["Se l'azienda vende al banco, in Fisco e IVA → Corrispettivi trovi gli incassi giornalieri trasmessi dal registratore telematico, con i totali divisi per aliquota IVA."] },
    ],
  },
  {
    id: "faq", titolo: "Domande frequenti", sezioni: [
      { t: "Non vedo una voce del menu", p: ["Le voci dipendono dai moduli attivi per l'azienda e dai permessi del tuo utente. Chiedi all'amministratore di abilitarla."] },
      { t: "Non riesco a modificare una fattura", p: ["Una fattura inviata allo SDI non si può più modificare. Se è sbagliata, si corregge con una nota di credito e una nuova fattura. Solo le fatture scartate si possono correggere e reinviare."] },
      { t: "Non riesco a salvare", p: ["Leggi il messaggio rosso che compare in basso: indica il campo da sistemare (per esempio codice fiscale mancante, natura IVA assente su una riga a 0%, rate che non tornano con il totale). I campi da correggere sono evidenziati."] },
      { t: "Ho sbagliato azienda", p: ["Se hai creato una bozza nell'azienda sbagliata, eliminala (si può fare finché è in bozza) e ricreala nell'azienda giusta."] },
      { t: "Stampare questa guida", p: ["Premi \"Scarica PDF\" in alto in questa pagina e scegli \"Salva come PDF\" come stampante per conservarne una copia."] },
    ],
  },
];
