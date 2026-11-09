import { useState } from "react";
import { PageHeader } from "@/components/Common";
import { useAuth, canSend } from "@/context/AuthContext";
import { useConti } from "@/components/ContoSelect";
import { ContiTab } from "@/components/coge/ContiTab";
import { TabellaTab } from "@/components/coge/TabellaTab";
import { ParametriTab } from "@/components/coge/ParametriTab";

const TABS = [["conti", "Piano dei conti"], ["causali", "Causali contabili"], ["iva", "Codici IVA"], ["parametri", "Parametri"]];

export default function PianoConti() {
  const { user } = useAuth();
  const canEdit = canSend(user);
  const [tab, setTab] = useState("conti");
  const [conti, reload] = useConti();
  return (
    <div>
      <PageHeader eyebrow="Contabilità generale" title="Piano dei conti e tabelle" />
      <div className="mb-5 flex flex-wrap gap-2">
        {TABS.map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`coge-tab-${k}`}
            className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-colors ${tab === k ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>{l}</button>
        ))}
      </div>
      {tab === "conti" && <ContiTab conti={conti} reload={reload} canEdit={canEdit} />}
      {(tab === "causali" || tab === "iva") && <TabellaTab key={tab} kind={tab} conti={conti} canEdit={canEdit} />}
      {tab === "parametri" && <ParametriTab conti={conti} canEdit={canEdit} />}
    </div>
  );
}
