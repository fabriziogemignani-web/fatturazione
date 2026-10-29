import { useNavigate } from "react-router-dom";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useCompany } from "@/context/CompanyContext";

export const CompanySwitcher = ({ onNav }) => {
  const { companies, current, setCurrent } = useCompany();
  const navigate = useNavigate();
  if (!companies?.length) return null;
  return (
    <div>
      <div className="mb-1.5 px-1 text-[10px] uppercase tracking-[0.2em] text-slate-500">Azienda attiva</div>
      <Select value={current} onValueChange={(v) => { setCurrent(v); navigate("/dashboard"); onNav?.(); }}>
        <SelectTrigger className="border-slate-700 bg-slate-800 text-left text-white" data-testid="company-switcher"><SelectValue /></SelectTrigger>
        <SelectContent className="bg-white">
          {companies.map((c) => (
            <SelectItem key={c.id} value={c.id} data-testid={`company-option-${c.id}`}>{c.denominazione}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
};
