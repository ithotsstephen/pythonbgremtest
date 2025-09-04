import os
import io
import os
import io
from flask import Flask, request, render_template, send_file, url_for, jsonify
from rembg import remove
from PIL import Image
from flask_cors import CORS

UPLOAD_FOLDER = 'uploads'
RESULT_FOLDER = 'results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULT_FOLDER'] = RESULT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024  # 12 MB limit

# Allow CORS for the API endpoint (adjust origins in production)
CORS(app, resources={r"/remove": {"origins": "*"}})

@app.route('/', methods=['GET', 'POST'])
def index():
    # Retain original form flow for local usage (non-static deployment)
    if request.method == 'POST':
        file = request.files.get('image')
        if not file:
            return render_template('index.html', error='No file provided')
        filename = file.filename
        input_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(input_path)
        uploaded_img = url_for('uploaded_file', filename=filename)
        try:
            with open(input_path, 'rb') as inp:
                output_bytes = remove(inp.read())
            output_img = Image.open(io.BytesIO(output_bytes))
        except Exception as e:
            return render_template('index.html', error=f'Processing failed: {e}')
        result_filename = filename + '.png'
        output_path = os.path.join(RESULT_FOLDER, result_filename)
        output_img.save(output_path)
        preview_img = url_for('result_file', filename=result_filename)
        download_link = preview_img
        return render_template('index.html',
                               preview_img=preview_img,
                               download_link=download_link,
                               uploaded_img=uploaded_img)
    return render_template('index.html')

@app.post('/remove')
def remove_background_api():
    """API endpoint: accepts multipart/form-data with 'image'; returns PNG."""
    file = request.files.get('image')
    if not file:
        return jsonify({'error': 'image file field "image" is required'}), 400
    try:
        input_bytes = file.read()
        if not input_bytes:
            return jsonify({'error': 'empty file'}), 400
        output_bytes = remove(input_bytes)
    except Exception as e:
        return jsonify({'error': f'processing failed: {e}'}), 500
    return send_file(
        io.BytesIO(output_bytes),
        mimetype='image/png',
        as_attachment=False,
        download_name='result.png'
    )

@app.get('/health')
def health():
    return {'status': 'ok'}

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename))

@app.route('/results/<filename>')
def result_file(filename):
    return send_file(os.path.join(RESULT_FOLDER, filename))

if __name__ == '__main__':
    app.run(debug=True)
