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
    doc_id = data.get('docId')

    if not pdf_url:
        return jsonify({'error': 'pdfUrl is required'}), 400

    try:
        # SYNC conversion (no job/check polling)
        convert_resp = requests.post(
            "https://api.pdf.co/v1/pdf/convert/to/text",
            headers={
                "Content-Type": "application/json",
                "x-api-key": PDF_CO_API_KEY,
            },
            json={
                "url": pdf_url,
                "async": False
            },
            timeout=120
        )

        convert_result = convert_resp.json()

        if not convert_resp.ok or convert_result.get("error"):
            return jsonify({
                'error': convert_result.get("message", "PDF conversion failed"),
                'details': convert_result
            }), 400

        result_url = convert_result.get("url")
        if not result_url:
            return jsonify({'error': 'No result URL returned from PDF.co'}), 400

        # Download extracted text
        text_resp = requests.get(result_url, timeout=120)
        if not text_resp.ok:
            return jsonify({'error': 'Failed to download extracted text'}), 400

        extracted_text = text_resp.text

        return jsonify({
            'docId': doc_id,
            'text': extracted_text
        })

    except requests.Timeout:
        return jsonify({'error': 'Request timed out. Try smaller PDFs.'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
