from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import time
import threading
import requests

app = Flask(__name__)
CORS(app)

PDF_CO_API_KEY = os.environ.get("PDF_CO_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
EMBEDDER_URL = os.environ.get("EMBEDDER_URL", "https://embedder-document.onrender.com/embed")

def supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }

def update_hoa_document(doc_id: str, payload: dict):
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        print("[supabase] Missing env vars; cannot update HOADocuments.")
        return False

    url = f"{SUPABASE_URL}/rest/v1/HOADocuments?HOADocumentID=eq.{doc_id}"
    resp = requests.patch(url, headers=supabase_headers(), json=payload, timeout=30)
    if not resp.ok:
        print("[supabase] Update failed:", resp.status_code, resp.text)
        return False
    return True

def pdfco_create_job(pdf_url: str):
    resp = requests.post(
        "https://api.pdf.co/v1/pdf/convert/to/text",
        headers={"Content-Type": "application/json", "x-api-key": PDF_CO_API_KEY},
        json={"url": pdf_url, "async": True},
        timeout=30
    )
    data = resp.json()
    if (not resp.ok) or data.get("error"):
        raise RuntimeError(data.get("message", "PDF.co create job failed"))
    return data

def pdfco_check_job(job_id: str):
    resp = requests.post(
        "https://api.pdf.co/v1/job/check",
        headers={"x-api-key": PDF_CO_API_KEY},
        json={"jobid": job_id},
        timeout=30
    )
    data = resp.json()
    if not resp.ok:
        raise RuntimeError(f"PDF.co job check failed: {resp.status_code} {resp.text[:200]}")
    return data

def pdfco_fetch_result_text(result_url: str):
    resp = requests.get(result_url, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"Failed to fetch result file: {resp.status_code}")
    return resp.text

def trigger_embedder():
    try:
        r = requests.post(EMBEDDER_URL, timeout=30)
        if not r.ok:
            print("[embedder] Failed:", r.status_code, r.text[:300])
        else:
            print("[embedder] Triggered OK")
    except Exception as e:
        print("[embedder] Error:", str(e))

def background_wait_and_finalize(doc_id: str, job_id: str, result_url: str, max_wait_seconds: int = 1800):
    print(f"[bg] Start polling job={job_id} docId={doc_id}")
    start = time.time()
    poll_interval = 10

    update_hoa_document(doc_id, {
        "pdfco_job_id": job_id,
        "extraction_status": "working",
        "extraction_error": None,
    })

    while time.time() - start < max_wait_seconds:
        try:
            status_data = pdfco_check_job(job_id)
            status = status_data.get("status")
        except Exception as e:
            print("[bg] job check error:", str(e))
            time.sleep(poll_interval)
            continue

        if status == "success":
            try:
                text = pdfco_fetch_result_text(result_url)
            except Exception as e:
                update_hoa_document(doc_id, {
                    "extraction_status": "failed",
                    "extraction_error": f"fetch_result_failed: {str(e)}",
                })
                return

            ok = update_hoa_document(doc_id, {
                "content": text,
                "extraction_status": "success",
                "extraction_error": None,
            })

            if ok:
                trigger_embedder()
            return

        if status in ("failed", "aborted"):
            update_hoa_document(doc_id, {
                "extraction_status": "failed",
                "extraction_error": f"pdfco_status_{status}",
            })
            return

        time.sleep(poll_interval)

    update_hoa_document(doc_id, {
        "extraction_status": "failed",
        "extraction_error": f"timeout_after_{max_wait_seconds}s",
    })

@app.route("/")
def home():
    return "PDF Extractor is running!"

@app.route("/extract-text", methods=["POST"])
def extract_text():
    data = request.get_json() or {}
    pdf_url = data.get("pdfUrl")
    doc_id = data.get("docId")

    if not pdf_url or not doc_id:
        return jsonify({"error": "pdfUrl and docId are required"}), 400
    if not PDF_CO_API_KEY:
        return jsonify({"error": "Server missing PDF_CO_API_KEY"}), 500

    try:
        job_data = pdfco_create_job(pdf_url)
        job_id = job_data.get("jobId")
        result_url = job_data.get("url")

        if not job_id or not result_url:
            return jsonify({"error": "PDF.co did not return jobId/url"}), 500

        threading.Thread(
            target=background_wait_and_finalize,
            args=(doc_id, job_id, result_url),
            daemon=True,
        ).start()

        return jsonify({"docId": doc_id, "jobId": job_id, "status": "started"}), 202

    except Exception as e:
        update_hoa_document(doc_id, {
            "extraction_status": "failed",
            "extraction_error": str(e),
        })
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


