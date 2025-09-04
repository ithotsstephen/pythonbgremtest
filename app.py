import os
import io
from flask import Flask, request, render_template, send_file, url_for
from rembg import remove
from PIL import Image

UPLOAD_FOLDER = 'uploads'
RESULT_FOLDER = 'results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULT_FOLDER'] = RESULT_FOLDER

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files['image']
        if file:
            input_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(input_path)
            with open(input_path, 'rb') as inp:
                output = remove(inp.read())
            output_img = Image.open(io.BytesIO(output))
            output_path = os.path.join(RESULT_FOLDER, file.filename + '.png')
            output_img.save(output_path)
            from flask import url_for
            result_filename = file.filename + '.png'
            preview_img = url_for('result_file', filename=result_filename)
            download_link = url_for('result_file', filename=result_filename)
            original_img = url_for('uploaded_file', filename=file.filename)
            return render_template('index.html',
                                   original_img=original_img,
                                   preview_img=preview_img,
                                   download_link=download_link,
                                   result_filename=result_filename)
    return render_template('index.html')

@app.route('/adjust')
def adjust():
    from PIL import ImageEnhance
    fname = request.args.get('file')
    if not fname:
        return 'missing file', 400
    if '/' in fname or '..' in fname:
        return 'bad name', 400
    path = os.path.join(RESULT_FOLDER, fname)
    if not os.path.exists(path):
        return 'not found', 404
    try:
        b = float(request.args.get('brightness', '1'))
        s = float(request.args.get('sharpness', '1'))
    except ValueError:
        return 'bad params', 400
    try:
        img = Image.open(path).convert('RGBA')
        if b != 1:
            img = ImageEnhance.Brightness(img).enhance(b)
        if s != 1:
            img = ImageEnhance.Sharpness(img).enhance(s)
        bio = io.BytesIO()
        img.save(bio, format='PNG')
        bio.seek(0)
        return send_file(bio, mimetype='image/png')
    except Exception as e:
        return f'error {e}', 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename))

@app.route('/results/<filename>')
def result_file(filename):
    return send_file(os.path.join(RESULT_FOLDER, filename))

if __name__ == '__main__':
    app.run(debug=True)
