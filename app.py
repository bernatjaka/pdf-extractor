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
    data = request.get_json()
    pdf_url = data.get('pdfUrl')
    doc_id = data.get('docId')  # Optional

    if not pdf_url:
        return jsonify({'error': 'pdfUrl is required'}), 400

    try:
        # Create the asynchronous job at PDF.co
        create_job_resp = requests.post(
            "https://api.pdf.co/v1/pdf/convert/to/text",
            headers={
                "Content-Type": "application/json",
                "x-api-key": PDF_CO_API_KEY,
            },
            json={
                "url": pdf_url,
                "async": True  # Use async mode
            }
        )
        create_job_result = create_job_resp.json()
        if not create_job_resp.ok or create_job_result.get("error"):
            return jsonify({'error': create_job_result.get("message", "Failed to create async job")}), 400

        job_id = create_job_result.get("jobId")
        result_url = create_job_result.get("url")
        job_status = create_job_result.get("status")
        print("[extract-text] Job created with ID:", job_id)

        # Poll for job completion
        MAX_POLL_SECONDS = 3000
        POLL_INTERVAL = 10
        start_time = time.time()
        extracted_text = ""

        while time.time() - start_time < MAX_POLL_SECONDS:
            if job_status == "success":
                print("[extract-text] Job succeeded. Fetching extracted text...")
                result_resp = requests.get(result_url, headers={"x-api-key": PDF_CO_API_KEY})
                extracted_text = result_resp.text
                break
            elif job_status in ["failed", "aborted"]:
                return jsonify({'error': f"Async job {job_id} failed with status: {job_status}"}), 400
            print(f"[extract-text] Job {job_id} status: {job_status}. Waiting {POLL_INTERVAL} seconds...")
            time.sleep(POLL_INTERVAL)
            status_resp = requests.get(f"https://api.pdf.co/v1/job/check?jobid={job_id}", headers={"x-api-key": PDF_CO_API_KEY})
            status_result = status_resp.json()
            job_status = status_result.get("status")

        if not extracted_text:
            return jsonify({'error': f"Async job did not complete within {MAX_POLL_SECONDS} seconds."}), 400

        return jsonify({'docId': doc_id, 'text': extracted_text})

    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


