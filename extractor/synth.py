"""Make SYNTHETIC invoices (fake vendors, fake numbers) plus ground truth and
simulated model responses for --dry-run.

Run: python -m extractor.synth
Writes inbox/*.pdf|png, truth/*.json (what is printed), fixtures/*.json
(a HAND-MADE stand-in for model output; see FIXTURE_ERRORS). Nothing here is real.
"""
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

VENDORS = ["Northwind Test Supplies", "Blue Harbor Demo Co", "Acme Fictional Ltd", "Granite Peak Sample Inc",
           "Lumen Placeholder LLC", "Sandbox Freight Co", "Orchard Mock Foods", "Pixel Dummy Studio"]
ITEMS = [("Office chair", "120.00"), ("Printer paper (box)", "24.50"), ("USB-C cable", "9.99"), ("Consulting hour", "85.00"),
         ("Desk lamp", "32.00"), ("Shipping", "15.00"), ("Monitor stand", "45.75"), ("Toner cartridge", "68.40")]

# Mistakes injected into the simulated model response. key = file stem.
FIXTURE_ERRORS = {
    "inv_04": ("total", "misread digit"),            # total off by a digit -> totals check should catch
    "inv_06": ("drop_line", "model skipped a line"),  # missing line -> line sum != subtotal
    "inv_08": ("vendor_typo", "vendor misspelled"),   # passes every check; only field accuracy sees it
    "inv_09": ("low_conf", "model unsure"),           # right values, confidence 0.55
}


def q(x):
    return Decimal(x).quantize(Decimal("0.01"))


def make(i, rng, today):
    items = []
    for d, p in rng.sample(ITEMS, rng.randint(1, 4)):
        qty = Decimal(rng.choice(["1", "2", "3", "5", "10", "1.5"]))
        price = q(p)
        items.append({"description": d, "quantity": str(qty), "unit_price": str(price), "amount": str(q(qty * price))})
    sub = sum(Decimal(x["amount"]) for x in items)
    rate = rng.choice([Decimal("0"), Decimal("0.05"), Decimal("0.10")])
    tax = q(sub * rate)
    return {"vendor": VENDORS[i % len(VENDORS)], "invoice_number": f"INV-{1000 + i * 7}",
            "invoice_date": str(today - timedelta(days=rng.randint(5, 400))),
            "subtotal": str(sub), "tax": str(tax), "total": str(sub + tax), "currency": "USD",
            "line_items": items, "confidence": 0.95}


def build_set(n=12, seed=7, today=None):
    rng = random.Random(seed)
    today = today or date(2026, 11, 1)  # fixed so the set is reproducible
    docs = {f"inv_{i:02d}": make(i, rng, today) for i in range(1, n + 1)}
    # planted problems in the DOCUMENTS themselves
    docs["inv_10"] = {**docs["inv_01"]}                                   # same vendor+number as inv_01 -> duplicate
    docs["inv_11"] = {**docs["inv_03"], "invoice_number": "INV-9001",
                      "invoice_date": "2099-01-01"}    # future date
    docs["inv_12"] = {**docs["inv_05"], "invoice_number": "INV-9002",
                      "total": str(Decimal(docs["inv_05"]["total"]) + Decimal("10.00"))}  # printed total is wrong
    return docs


def fixture_for(stem, truth):
    r = json.loads(json.dumps(truth))
    kind = FIXTURE_ERRORS.get(stem, (None,))[0]
    if kind == "total":
        t = Decimal(r["total"]); r["total"] = str(t + Decimal("90.00"))
    elif kind == "drop_line" and len(r["line_items"]) > 1:
        r["line_items"].pop()
    elif kind == "drop_line":
        r["tax"] = str(Decimal(r["tax"]) + 1)
    elif kind == "vendor_typo":
        r["vendor"] = r["vendor"].replace("o", "0", 1)
    elif kind == "low_conf":
        r["confidence"] = 0.55
    return r


def render_pdf(doc, path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    c.setFont("Helvetica-Bold", 16); c.drawString(50, y, doc["vendor"]); y -= 22
    c.setFont("Helvetica", 9); c.drawString(50, y, "SYNTHETIC SAMPLE - not a real invoice"); y -= 30
    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"Invoice No: {doc['invoice_number']}"); y -= 16
    c.drawString(50, y, f"Date: {doc['invoice_date']}"); y -= 30
    c.drawString(50, y, "Description"); c.drawString(300, y, "Qty"); c.drawString(360, y, "Unit"); c.drawString(450, y, "Amount"); y -= 16
    for li in doc["line_items"]:
        c.drawString(50, y, li["description"]); c.drawString(300, y, li["quantity"])
        c.drawString(360, y, li["unit_price"]); c.drawString(450, y, li["amount"]); y -= 16
    y -= 14
    for label, k in (("Subtotal", "subtotal"), ("Tax", "tax"), ("TOTAL", "total")):
        c.drawString(360, y, f"{label}:"); c.drawString(450, y, f"{doc[k]} {doc['currency']}" if k == "total" else doc[k]); y -= 16
    c.save()


def render_png(doc, path):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (900, 700), "white")
    d = ImageDraw.Draw(img)
    f = ImageFont.load_default(size=20)
    y = 30
    for line in [doc["vendor"], "SYNTHETIC SAMPLE - not a real invoice", "",
                 f"Invoice No: {doc['invoice_number']}", f"Date: {doc['invoice_date']}", ""]:
        d.text((40, y), line, fill="black", font=f); y += 30
    for li in doc["line_items"]:
        d.text((40, y), f"{li['description']}   {li['quantity']} x {li['unit_price']} = {li['amount']}", fill="black", font=f); y += 30
    y += 20
    for label, k in (("Subtotal", "subtotal"), ("Tax", "tax"), ("TOTAL", "total")):
        d.text((40, y), f"{label}: {doc[k]}" + (f" {doc['currency']}" if k == "total" else ""), fill="black", font=f); y += 30
    img.save(path)


def main():
    for d in ("inbox", "truth", "fixtures"):
        Path(d).mkdir(exist_ok=True)
    for stem, doc in build_set().items():
        n = int(stem[4:])
        (render_png if n % 4 == 0 else render_pdf)(doc, Path("inbox") / f"{stem}.{'png' if n % 4 == 0 else 'pdf'}")
        Path("truth", f"{stem}.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
        Path("fixtures", f"{stem}.json").write_text(json.dumps(fixture_for(stem, doc), indent=2), encoding="utf-8")
    print("wrote 12 synthetic invoices")


if __name__ == "__main__":
    main()
