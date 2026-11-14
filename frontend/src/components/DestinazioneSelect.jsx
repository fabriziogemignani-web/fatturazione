const label = (d) => [d.denominazione, d.indirizzo, [d.cap, d.comune, d.provincia && `(${d.provincia})`].filter(Boolean).join(" ")].filter(Boolean).join(" · ");

export const DestinazioneSelect = ({ destinazioni = [], onPick, disabled, testId = "destinazione-select" }) => {
  if (!destinazioni.length) return null;
  return (
    <select disabled={disabled} defaultValue="" onChange={(e) => { const d = destinazioni[Number(e.target.value)]; if (d) onPick({ denominazione: d.denominazione || "", indirizzo: d.indirizzo, cap: d.cap || "", comune: d.comune, provincia: d.provincia || "" }); e.target.value = ""; }}
      className="mt-2 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid={testId}>
      <option value="">Scegli una destinazione del cliente…</option>
      {destinazioni.map((d, i) => <option key={i} value={i}>{label(d)}</option>)}
    </select>
  );
};
