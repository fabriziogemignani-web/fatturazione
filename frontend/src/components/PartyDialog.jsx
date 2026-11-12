import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { PaSearch } from "@/components/PaSearch";
import { downloadEstratto } from "@/components/SollecitoDialog";
import { FileText, FileSpreadsheet } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { NATURE } from "@/lib/fe";
import { api, errMsg } from "@/lib/api";
import { useCompany } from "@/context/CompanyContext";
import { mods, vede } from "@/lib/moduli";
import { IntentiCard } from "@/components/Intenti";
import { ContoSelect, useConti } from "@/components/ContoSelect";
import { AssoggettamentoFornitore } from "@/components/AssoggettamentoFornitore";
import { ListinoCliente } from "@/components/ListinoCliente";

const EMPTY = {
  denominazione: "", partita_iva: "", codice_fiscale: "", codice_destinatario: "0000000", pec: "",
  email: "", telefono: "", indirizzo: "", cap: "", comune: "", provincia: "", nazione: "IT",
  natura_default: "", riferimento_normativo: "", intento_protocollo: "", intento_data: "",
  pubblica_amministrazione: false, split_payment: false, bollo_addebito: false, conto_costo: "", detraibilita_iva: 100,
  soggetto_ritenuta: false, ritenuta_tipo: "RT01", ritenuta_aliquota: 20, ritenuta_base: 100, ritenuta_causale: "A", cassa_tipo: "", cassa_aliquota: 4, cassa_ritenuta: false, listino: [],
};

const FIELDS = [
  ["denominazione", "Ragione sociale / Nome", "sm:col-span-2"],
  ["partita_iva", "Partita IVA"],
  ["codice_fiscale", "Codice fiscale"],
  ["codice_destinatario", "Codice destinatario SDI"],
  ["pec", "PEC"],
  ["email", "Email"],
  ["telefono", "Telefono"],
  ["indirizzo", "Indirizzo", "sm:col-span-2"],
  ["cap", "CAP"],
  ["comune", "Comune"],
  ["provincia", "Provincia (sigla)"],
  ["nazione", "Nazione"],
];

export const PartyDialog = ({ open, onOpenChange, tipo, party, onSaved }) => {
  const m = mods(useCompany().company);
  const attive = m.fatture_attive;
  const { company: co } = useCompany();
  const scheda = m.contabilita && vede(co, "mastrini");
  const navigate = useNavigate();
  const isForn = (party?.tipo || tipo) === "fornitore";
  const [conti] = useConti(open && isForn && m.contabilita);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const { fail, reset, value } = useFieldErrors();

  useEffect(() => {
    if (open) { setForm(party ? { ...EMPTY, ...party } : EMPTY); reset(); }
  }, [open, party, reset]);

  const save = async () => {
    setSaving(true);
    try {
      const body = { ...form, tipo: party?.tipo || tipo };
      const { data } = party ? await api.put(`/parties/${party.id}`, body) : await api.post("/parties", body);
      toast.success(party ? "Anagrafica aggiornata" : "Anagrafica creata");
      onSaved(data);
      onOpenChange(false);
    } catch (e) {
      fail(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto bg-white sm:max-w-2xl" data-testid="party-dialog">
        <FieldErrors value={value}>
        <DialogHeader>
          <DialogTitle>{party?.da_verificare ? "Verifica fornitore creato dalla fattura" : party ? "Modifica anagrafica" : `Nuovo ${tipo === "fornitore" ? "fornitore" : "cliente"}`}</DialogTitle>
          {party?.da_verificare && <p className="text-xs text-amber-700" data-testid="party-verifica-note">Dati letti dall'XML della fattura{party.iban ? ` (IBAN ${party.iban})` : ""}{party.rea ? ` · REA ${party.rea}` : ""}. Controlla e completa, poi salva per confermare.</p>}
        </DialogHeader>
        {(party?.tipo || tipo) === "cliente" && (
          <div className="space-y-3 rounded-lg border border-sky-200 bg-sky-50 p-4" data-testid="party-pa-section">
            <label className="flex items-center justify-between gap-3 text-sm text-slate-700">
              Addebita il bollo virtuale (2 €) al cliente sulle fatture esenti
              <Switch checked={!!form.bollo_addebito} onCheckedChange={(v) => setForm({ ...form, bollo_addebito: v })} data-testid="party-bollo-switch" />
            </label>
            <label className="flex items-center justify-between gap-3 text-sm font-semibold text-slate-800">
              Pubblica Amministrazione (fattura FPA12)
              <Switch checked={!!form.pubblica_amministrazione} data-testid="party-pa-switch"
                onCheckedChange={(v) => setForm({ ...form, pubblica_amministrazione: v, split_payment: v ? form.split_payment : false, codice_destinatario: v ? (form.codice_destinatario === "0000000" ? "" : form.codice_destinatario) : (form.codice_destinatario || "0000000") })} />
            </label>
            {form.pubblica_amministrazione && (
              <label className="flex items-center justify-between gap-3 text-sm text-slate-700">
                Scissione dei pagamenti (split payment, art. 17-ter)
                <Switch checked={!!form.split_payment} onCheckedChange={(v) => setForm({ ...form, split_payment: v })} data-testid="party-split-switch" />
              </label>
            )}
            {form.pubblica_amministrazione && (
              <PaSearch onPick={(r) => {
                setForm((f) => ({ ...f, denominazione: f.denominazione || r.ente, codice_fiscale: r.codice_fiscale || f.codice_fiscale, codice_destinatario: r.codice_uo,
                  indirizzo: r.indirizzo || f.indirizzo, cap: r.cap || f.cap, pec: r.pec || f.pec, nazione: "IT" }));
                toast.success(`Codice ufficio ${r.codice_uo} inserito`);
              }} />
            )}
          </div>
        )}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {FIELDS.map(([k, label, cls]) => (
            <Field key={k} name={k} label={k === "codice_destinatario" && form.pubblica_amministrazione ? "Codice univoco ufficio PA (6 caratteri)" : k === "codice_fiscale" && (form.nazione || "IT").trim().toUpperCase() === "IT" ? "Codice fiscale *" : label} className={cls}>
              <Input data-testid={`party-${k.replace(/_/g, "-")}-input`} value={form[k] || ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
            </Field>
          ))}
        </div>
        <p className="text-xs text-slate-500">{form.pubblica_amministrazione ? "Il codice univoco ufficio (6 caratteri) si trova sull'Indice delle PA (indicepa.gov.it)." : "Usa 0000000 come codice destinatario se il cliente riceve via PEC o è un privato."}</p>
        {isForn && (
          <Field label="IVA detraibile % (es. carburante 40, telefonia 50)" name="detraibilita_iva">
            <Input type="number" min={0} max={100} step="1" value={form.detraibilita_iva ?? 100} onChange={(e) => setForm({ ...form, detraibilita_iva: e.target.value === "" ? 0 : Number(e.target.value) })} data-testid="party-detraibilita-input" />
          </Field>
        )}
        {isForn && (
          <Field label="IBAN per i bonifici" name="iban">
            <Input className="mono" value={form.iban || ""} placeholder="IT60X0542811101000000123456" onChange={(e) => setForm({ ...form, iban: e.target.value.replace(/\s+/g, "").toUpperCase() })} data-testid="party-iban-input" />
          </Field>
        )}
        {isForn && <AssoggettamentoFornitore form={form} setForm={setForm} />}
        {!isForn && (
          <div className="grid grid-cols-1 gap-4 rounded-lg border border-slate-200 p-3 sm:grid-cols-4" data-testid="party-appoggio">
            <div className="text-xs font-semibold text-slate-600 sm:col-span-4">Banca d'appoggio per le Ri.Ba.</div>
            {[["appoggio_banca", "Banca", "sm:col-span-2"], ["appoggio_abi", "ABI"], ["appoggio_cab", "CAB"]].map(([k, label, cls]) => (
              <Field key={k} name={k} label={label} className={cls}>
                <Input data-testid={`party-${k.replace(/_/g, "-")}-input`} value={form[k] || ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
              </Field>
            ))}
          </div>
        )}
        {!isForn && attive && <ListinoCliente form={form} setForm={setForm} />}
        {isForn && m.contabilita && (
          <Field label="Contropartita di acquisto (conto di costo)" name="conto_costo">
            <ContoSelect conti={conti} tipi={["costo", "attivita"]} value={form.conto_costo} onChange={(v) => setForm({ ...form, conto_costo: v })} allowEmpty="Quella predefinita dell'azienda" testId="party-conto-costo-select" />
          </Field>
        )}
        <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-4" data-testid="party-iva-section">
          <div className="text-sm font-semibold text-slate-800">Regime IVA del {isForn ? "fornitore" : "cliente"}</div>
          <Field label="Codice IVA / esenzione applicata" name="natura_default">
            <Select value={form.natura_default || "ORD"} onValueChange={(v) => setForm({ ...form, natura_default: v === "ORD" ? "" : v })}>
              <SelectTrigger className="bg-white" data-testid="party-natura-select"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-white max-h-72">
                <SelectItem value="ORD">Ordinario (IVA dell'articolo)</SelectItem>
                {NATURE.map(([k, l]) => <SelectItem key={k} value={k}>{`Esente/non imponibile ${l}`}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          {form.natura_default && form.natura_default !== "N3.5" && (
            <Field label="Riferimento normativo (opzionale)" name="riferimento_normativo">
              <Input value={form.riferimento_normativo || ""} onChange={(e) => setForm({ ...form, riferimento_normativo: e.target.value })} placeholder="es. Esente art. 10 n. 18 DPR 633/72" data-testid="party-riferimento-input" />
            </Field>
          )}
          {form.natura_default === "N3.5" && (
            <div data-testid="party-intento-fields">
              {party?.id ? <IntentiCard partyId={party.id} /> : <p className="text-xs text-amber-700">Salva il cliente, poi riapri la scheda per inserire le dichiarazioni d'intento con il plafond.</p>}
            </div>
          )}
        </div>
        <DialogFooter className="gap-2">
          {party?.id && scheda && <Button variant="outline" onClick={() => { onOpenChange(false); navigate(`/contabilita/mastrini?party=${party.id}`); }} data-testid="party-dialog-scheda-btn"><FileSpreadsheet className="mr-2 h-4 w-4" />Scheda contabile</Button>}
          {party?.id && party.tipo === "cliente" && attive && <Button variant="outline" className="sm:mr-auto" onClick={() => downloadEstratto(party.id, party.denominazione)} data-testid="party-dialog-estratto-btn"><FileText className="mr-2 h-4 w-4" />Estratto conto PDF</Button>}
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="party-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={saving} data-testid="party-save-btn">{saving ? "Salvataggio…" : "Salva"}</Button>
        </DialogFooter>
        </FieldErrors>
      </DialogContent>
    </Dialog>
  );
};
