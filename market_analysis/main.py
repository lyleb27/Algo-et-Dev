import os
import json
import tempfile
import smtplib
import traceback
from typing import List, Dict, Any
from fastapi import FastAPI, Form, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
import requests
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

app = FastAPI()
templates = Jinja2Templates(directory="templates")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
# SMTP config (set as env vars in production)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")


# ---------- LLM call with streaming safe parsing ----------
def call_llm(prompt: str, model: str = "llama3", prefer_json: bool = True) -> str:
    """
    Call Ollama (or other) and return aggregated text.
    If prefer_json=True, we ask the model to respond with JSON (see prompt design).
    This function supports streaming responses and concatenates lines.
    """
    try:
        # request streaming (robust against streaming JSON lines)
        resp = requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": True},
            stream=True,
            timeout=60
        )
    except Exception as e:
        print("LLM connection error:", e)
        return ""

    full_text = ""
    try:
        # read streaming lines
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            # raw might already be JSON text (like '{"response": "..."}') or plain text
            try:
                parsed = json.loads(raw)
                # Ollama may use key 'response' or 'text'
                if isinstance(parsed, dict):
                    # try common keys
                    chunk = parsed.get("response") or parsed.get("text") or parsed.get("output") or ""
                    full_text += chunk
                else:
                    # fallback: string
                    full_text += str(parsed)
            except json.JSONDecodeError:
                # sometimes it's plain text line
                full_text += raw
    except Exception as e:
        # if streaming failed, fallback to single JSON parse
        try:
            j = resp.json()
            # try to find content
            if isinstance(j, dict):
                full_text = j.get("response") or j.get("text") or j.get("output") or str(j)
            else:
                full_text = json.dumps(j)
        except Exception as e2:
            print("Error decoding LLM response:", e2)
            full_text = ""

    return full_text.strip()


# ---------- Utility: prompt builder ----------
def build_prompt_for_products(products: List[str], sector: str) -> str:
    """
    Builds a prompt that requests structured JSON for each product:
    Return a JSON list of objects { product, strengths, weaknesses, market_trend_score, est_share_pct, notes }.
    """
    products_list_text = ", ".join(products)
    prompt = f"""
Tu es un assistant spécialisé en études de marché. 
Pour CHAQUE produit de la liste ci-dessous, appartenant au secteur « {sector} », produis un tableau JSON où chaque élément contient exactement les clés suivantes :

- "product" (chaîne de caractères) — nom du produit  
- "summary" (texte court) — résumé synthétique du positionnement du produit  
- "strengths" (liste de chaînes courtes) — forces principales du produit  
- "weaknesses" (liste de chaînes courtes) — faiblesses principales du produit  
- "trend_score" (nombre entre 0 et 100 ; 100 = tendance très positive)  
- "estimated_share" (nombre entre 0 et 100 représentant le pourcentage estimé de part de marché ; la somme totale peut être approximative)  
- "metrics" (objet contenant : "price_level" (bas/moyen/élevé), "sentiment_score" (entre 0 et 1), "reviews_count" (entier représentant le nombre d’avis))

Réponds UNIQUEMENT avec du JSON valide (aucune explication, aucun texte supplémentaire, aucun markdown).

Exemple attendu :
[
  {{
    "product": "Exemple A",
    "summary": "Produit rapide et abordable.",
    "strengths": ["rapide", "bon rapport qualité-prix"],
    "weaknesses": ["autonomie moyenne"],
    "trend_score": 72,
    "estimated_share": 25,
    "metrics": {{"price_level": "moyen", "sentiment_score": 0.72, "reviews_count": 1200}}
  }},
  ...
]

Produits : {products_list_text}
Secteur : {sector}
"""

    return prompt.strip()


# ---------- PDF generation: table + chart + sections ----------
def generate_comparison_pdf(structured_data: List[Dict[str, Any]], filename: str = "rapport_comparatif.pdf") -> str:
    """
    structured_data: list of dicts as produced by the prompt parsing step.
    Produces a PDF with:
    - Title
    - Summary paragraphs per product
    - Comparison table
    - A bar chart of trend_score and share
    """
    # create a temp file path
    out_path = os.path.abspath(filename)
    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4

    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 50, "Étude de marché - Comparatif de produits")

    # Small intro
    c.setFont("Helvetica", 11)
    c.drawString(50, height - 75, "Synthèse automatique générée par LLM")

    # Product summaries
    y = height - 110
    for item in structured_data:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, f"{item.get('product', 'Produit')}:")
        y -= 16
        c.setFont("Helvetica", 10)
        summary = item.get("summary", "")
        # wrap text manually (simple)
        for line in split_text(summary, 80):
            c.drawString(60, y, line)
            y -= 12
        # strengths / weaknesses
        strengths = item.get("strengths", [])
        weaknesses = item.get("weaknesses", [])
        c.drawString(60, y, "Forces: " + (", ".join(strengths) if strengths else "-"))
        y -= 12
        c.drawString(60, y, "Faiblesses: " + (", ".join(weaknesses) if weaknesses else "-"))
        y -= 18
        if y < 150:
            c.showPage()
            y = height - 50

    # New page: comparison table
    c.showPage()
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Tableau comparatif")
    y = height - 80

    # Build table data: header + rows
    header = ["Produit", "Trend (0-100)", "Est. Share %", "Price", "Sentiment", "Reviews"]
    rows = [header]
    for item in structured_data:
        metrics = item.get("metrics", {})
        row = [
            item.get("product", ""),
            str(item.get("trend_score", "")),
            str(item.get("estimated_share", "")),
            metrics.get("price_level", ""),
            f"{metrics.get('sentiment_score','')}",
            str(metrics.get("reviews_count",""))
        ]
        rows.append(row)

    # create table
    table = Table(rows, colWidths=[130, 80, 80, 80, 80, 80])
    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (1,1), (-1,-1), 'CENTER'),
    ])
    table.setStyle(style)
    table.wrapOn(c, width - 100, height)
    table.drawOn(c, 50, y - (20 * len(rows)))

    # Add chart (trend_score and estimated_share)
    chart_path = generate_chart_png(structured_data)
    if chart_path:
        c.drawImage(chart_path, 50, 80, width=500, height=200, preserveAspectRatio=True, mask='auto')

    c.save()
    # cleanup chart file
    try:
        if chart_path and os.path.exists(chart_path):
            os.remove(chart_path)
    except Exception:
        pass

    return out_path


def split_text(text: str, width: int = 80):
    """Simple text wrapper by characters (for reportlab fixed drawing)."""
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        if len(cur) + 1 + len(w) <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def generate_chart_png(structured_data: List[Dict[str, Any]]) -> str:
    """Generates a simple bar chart of trend_score and estimated_share, returns PNG path."""
    labels = [d.get("product", "") for d in structured_data]
    trend = [float(d.get("trend_score", 0)) for d in structured_data]
    share = [float(d.get("estimated_share", 0)) for d in structured_data]

    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar([i-0.2 for i in x], trend, width=0.4, label="Trend (0-100)")
    ax.bar([i+0.2 for i in x], share, width=0.4, label="Estimated Share %")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha='right')
    ax.set_ylabel("Score / %")
    ax.legend()
    plt.tight_layout()

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    fig.savefig(path)
    plt.close(fig)
    return path


# ---------- Email sending (background) ----------
def send_email_with_attachment(to_email: str, subject: str, body: str, attachment_path: str):
    """
    Simple SMTP email sender. Requires SMTP env variables set.
    """
    try:
        if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
            raise RuntimeError("SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASS env vars.")

        import email, email.mime.application, email.mime.text, email.mime.multipart
        msg = email.mime.multipart.MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(email.mime.text.MIMEText(body))

        with open(attachment_path, "rb") as f:
            part = email.mime.application.MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
        msg.attach(part)

        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [to_email], msg.as_string())
        server.quit()
        print("Email sent to", to_email)
    except Exception as e:
        print("Failed to send email:", e)
        traceback.print_exc()


# ---------- Routes ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/analyse_market", response_class=HTMLResponse)
def analyse_market(request: Request,
                   produits_raw: str = Form(...),
                   secteur: str = Form(...),
                   email_to: str = Form(None),
                   background_tasks: BackgroundTasks = None):

    """
    produits_raw: comma-separated product names or newline-separated
    """
    # parse products
    products = [p.strip() for p in produits_raw.replace("\r", "\n").split("\n") if p.strip()]
    if not products:
        # try comma-separated
        products = [p.strip() for p in produits_raw.split(",") if p.strip()]

    # Build structured prompt
    prompt = build_prompt_for_products(products, secteur)
    raw_llm = call_llm(prompt)

    # Try parse JSON from LLM output (robust)
    structured = []
    parse_error = None
    try:
        # Some LLMs return plain text before JSON; find first '['
        start = raw_llm.find('[')
        if start != -1:
            candidate = raw_llm[start:]
        else:
            candidate = raw_llm
        structured = json.loads(candidate)
        # validate: ensure list of dicts
        if not isinstance(structured, list):
            raise ValueError("LLM did not return a JSON list")
    except Exception as e:
        print("Failed to parse LLM JSON output:", e)
        parse_error = str(e)

        # fallback: create a simple structured object from raw text (best-effort)
        for prod in products:
            structured.append({
                "product": prod,
                "summary": raw_llm[:300],
                "strengths": [],
                "weaknesses": [],
                "trend_score": 50,
                "estimated_share": round(100/len(products), 1),
                "metrics": {"price_level": "unknown", "sentiment_score": 0.5, "reviews_count": 0}
            })

    # Generate PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmpf:
        pdf_path = tmpf.name
    # overwrite with our generator
    pdf_path = generate_comparison_pdf(structured, filename=pdf_path)


    return templates.TemplateResponse("result.html", {
        "request": request,
        "raw_llm": raw_llm,
        "structured": structured,
        "pdf_file": os.path.basename(pdf_path),
        "pdf_path": pdf_path,
        "parse_error": parse_error
    })


@app.get("/download/{filename}")
def download(filename: str):
    # temporary directory usage: assume previous pdf generated in current dir or tmp
    # if stored with absolute path, result template supplies pdf_path
    # try to find full path in cwd or /tmp
    candidates = [
        os.path.join(os.getcwd(), filename),
        os.path.join(tempfile.gettempdir(), filename)
    ]
    for p in candidates:
        if os.path.exists(p):
            return FileResponse(p, media_type="application/pdf", filename=filename)
    # As a fallback, if result gave absolute path, it should be used directly by clicking link in template.
    return {"error": "file not found"}


@app.post("/send_report")
def send_report(to_email: str = Form(...), pdf_path: str = Form(...), background_tasks: BackgroundTasks = None):
    """
    Sends the PDF by email in background.
    pdf_path should be the absolute path returned by analysis.
    """
    subject = "Rapport d'étude de marché"
    body = "Veuillez trouver en pièce jointe le rapport d'étude de marché généré automatiquement."
    if background_tasks:
        background_tasks.add_task(send_email_with_attachment, to_email, subject, body, pdf_path)
        return {"status": "enqueued"}
    else:
        # direct send (blocking)
        send_email_with_attachment(to_email, subject, body, pdf_path)
        return {"status": "sent"}

