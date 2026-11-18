# UI setup for iteration 101: upload one extra TEST_ passive invoice (ambiguous) into kept TEST_T101 company. Usage: python ui_setup_t101.py <cid> <piva>
import sys
import test_iteration101_ai_registrazione_consulente as t

t.ST["cid"], t.PIVA = sys.argv[1], sys.argv[2]
print(t.upload(t.xml("UI-9", f"{t.Y}-01-15", "09876543210", "TEST_T101 Servizi Generici Srl", [("Prestazione come da accordi", 300.0)])))
