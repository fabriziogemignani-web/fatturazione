import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api, errMsg } from "@/lib/api";

export const fetchXml = async (id) => {
  const res = await api.get(`/invoices/${id}/xml`, { responseType: "text" });
  return { xml: res.data, filename: res.headers["x-filename"] || "fattura.xml" };
};

export const downloadXml = async (id) => {
  try {
    const { xml, filename } = await fetchXml(id);
    const url = URL.createObjectURL(new Blob([xml], { type: "application/xml" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Scaricato ${filename}`);
  } catch (e) {
    toast.error(errMsg(e));
  }
};

export const XmlDialog = ({ open, onOpenChange, invoiceId }) => {
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!open) return;
    setData(null);
    fetchXml(invoiceId).then(setData).catch((e) => { toast.error(errMsg(e)); onOpenChange(false); });
  }, [open, invoiceId, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white sm:max-w-4xl" data-testid="xml-preview-dialog">
        <DialogHeader>
          <DialogTitle className="mono text-sm" data-testid="xml-filename">{data?.filename || "Generazione XML…"}</DialogTitle>
        </DialogHeader>
        <pre className="mono max-h-[60vh] overflow-auto rounded-lg bg-slate-950 p-4 text-xs leading-relaxed text-emerald-300" data-testid="xml-preview-content">
          {data?.xml || "…"}
        </pre>
        <div className="flex justify-end">
          <Button onClick={() => downloadXml(invoiceId)} data-testid="xml-dialog-download-btn"><Download className="mr-2 h-4 w-4" />Scarica XML</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
