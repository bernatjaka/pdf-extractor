from flask import Flask, request, jsonify
import fitz  # PyMuPDF
import requests

app = Flask(__name__)

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
        response = requests.get(pdf_url)
        if response.status_code != 200:
            return jsonify({'error': 'Failed to fetch PDF'}), 400

        pdf_bytes = response.content
        result = []

        with fitz.open(stream=pdf_bytes, filetype='pdf') as doc:
            for i, page in enumerate(doc):
                text = page.get_text()
                result.append({
                    'page': i + 1,
                    'text': text
                })

        return jsonify({'docId': doc_id, 'pages': result})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    from os import getenv
    port = int(getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
