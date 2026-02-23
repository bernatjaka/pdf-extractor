from flask import Flask, request, jsonify
from flask_cors import CORS  # <-- Import CORS
import requests
import os
import time

app = Flask(__name__)
CORS(app)  # <-- Enable CORS for all routes

# Hardcoded PDF.co API key
PDF_CO_API_KEY = "jakabernat3@gmail.com_hYCJ5kc8e3DfLtBiYK75gVZfwYBFBfDJRxhRcvWAlNzSFHvIfZflE5qAffPCqjla"

@app.route('/')
def home():
    return 'PDF Extractor is running!'

@app.route('/extract-text', methods=['POST'])
def extract_text():
    data = request.get_json() or {}
    pdf_url = data.get('pdfUrl')
    doc_id = data.get('docId')  # Optional

    if not pdf_url:
        return jsonify({'error': 'pdfUrl is required'}), 400

    try:
        # ✅ Create ASYNC job at PDF.co (fire)
        create_job_resp = requests.post(
            "https://api.pdf.co/v1/pdf/convert/to/text",
            headers={
                "Content-Type": "application/json",
                "x-api-key": PDF_CO_API_KEY,
            },
            json={
                "url": pdf_url,
                "async": True,
                # ✅ Helps when source URL is flaky/expiring (Drive/Dropbox/signed URLs)
                "cache": True
            },
            timeout=60
        )

        create_job_result = create_job_resp.json()
        if (not create_job_resp.ok) or create_job_result.get("error"):
            return jsonify({
                'error': create_job_result.get("message", "Failed to create async job"),
                'details': create_job_result
            }), 400

        job_id = create_job_result.get("jobId")
        result_url = create_job_result.get("url")
        job_status = create_job_result.get("status")  # often "working"

        if not job_id:
            return jsonify({'error': 'PDF.co did not return jobId', 'details': create_job_result}), 400
        if not result_url:
            return jsonify({'error': 'PDF.co did not return result url', 'details': create_job_result}), 400

        print("[extract-text] Job created:", job_id, "status:", job_status)

        # ✅ CHEAPER polling:
        # - Backoff waits
        # - Hard cap on checks (len(intervals))
        # This prevents 45-min loops and credit burn.
        intervals = [5, 10, 20, 40, 60, 60, 60, 60, 60, 60]  # max 10 job/check calls

        for wait in intervals:
            if job_status == "success":
                break
            if job_status in ["failed", "aborted"]:
                return jsonify({'error': f"Async job {job_id} failed with status: {job_status}"}), 400

            time.sleep(wait)

            status_resp = requests.get(
                f"https://api.pdf.co/v1/job/check?jobid={job_id}",
                headers={"x-api-key": PDF_CO_API_KEY},
                timeout=30
            )
            status_result = status_resp.json()
            job_status = status_result.get("status")
            print(f"[extract-text] Job {job_id} status: {job_status}")

        if job_status != "success":
            # ✅ Return job info so you can inspect it (and NOT keep polling forever)
            return jsonify({
                'error': f"Job did not finish after {len(intervals)} checks.",
                'docId': doc_id,
                'jobId': job_id,
                'lastStatus': job_status,
                'resultUrl': result_url
            }), 408

        # ✅ Fetch extracted text
        # NOTE: result_url is typically a signed S3 link; it usually does NOT require x-api-key
        result_resp = requests.get(result_url, timeout=120)
        if not result_resp.ok:
            return jsonify({
                'error': 'Failed to download extracted text',
                'docId': doc_id,
                'jobId': job_id,
                'resultUrl': result_url
            }), 400

        extracted_text = result_resp.text or ""
        if not extracted_text.strip():
            return jsonify({
                'error': 'Extracted text is empty (PDF may be scanned / needs OCR).',
                'docId': doc_id,
                'jobId': job_id
            }), 400

        return jsonify({'docId': doc_id, 'text': extracted_text})

    except requests.Timeout:
        return jsonify({'error': 'Timed out communicating with PDF.co. Try again or use smaller PDFs.'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
