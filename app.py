import os
import io
from flask import Flask, request, render_template, send_file, url_for, jsonify
from werkzeug.utils import secure_filename
from rembg import remove
from PIL import Image, ImageFont, ImageDraw

UPLOAD_FOLDER = 'uploads'
RESULT_FOLDER = 'results'
BACKGROUND_FOLDER = 'backgrounds'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)
os.makedirs(BACKGROUND_FOLDER, exist_ok=True)

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

@app.route('/upload_bg', methods=['POST'])
def upload_bg():
    file = request.files.get('bg')
    if not file:
        return jsonify({'error': 'no file'}), 400
    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'error': 'bad filename'}), 400
    path = os.path.join(BACKGROUND_FOLDER, filename)
    file.save(path)
    return jsonify({'filename': filename})

@app.route('/render')
def render_image():
    """Compose processed image with optional brightness/sharpness + background color or image."""
    from PIL import ImageEnhance
    fname = request.args.get('file')
    if not fname:
        return 'missing file', 400
    if '/' in fname or '..' in fname:
        return 'bad name', 400
    base_path = os.path.join(RESULT_FOLDER, fname)
    if not os.path.exists(base_path):
        return 'not found', 404
    try:
        b = float(request.args.get('brightness', '1'))
        s = float(request.args.get('sharpness', '1'))
    except ValueError:
        return 'bad params', 400
    color_hex = request.args.get('color')
    bg_image_name = request.args.get('bg_image')
    text = request.args.get('text', '').strip()
    text_color_hex = request.args.get('text_color', '000000')
    text_size = request.args.get('text_size', '48')
    text_font = request.args.get('text_font', '')
    text_bold = request.args.get('text_bold', '0') == '1'
    text_pos = request.args.get('text_pos', 'bc')
    rotate = request.args.get('rotate', '0')
    flip = request.args.get('flip', '')
    try:
        # load and basic adjustments
        img = Image.open(base_path).convert('RGBA')
        if b != 1:
            img = ImageEnhance.Brightness(img).enhance(b)
        if s != 1:
            img = ImageEnhance.Sharpness(img).enhance(s)
        composed = img
        # background composition
        if color_hex or bg_image_name:
            W, H = img.size
            if bg_image_name:
                if '/' in bg_image_name or '..' in bg_image_name:
                    return 'bad bg name', 400
                bg_path = os.path.join(BACKGROUND_FOLDER, bg_image_name)
                if not os.path.exists(bg_path):
                    return 'bg not found', 404
                bg_img = Image.open(bg_path).convert('RGBA')
                bw, bh = bg_img.size
                scale = max(W / bw, H / bh)
                new_size = (int(bw * scale), int(bh * scale))
                bg_img = bg_img.resize(new_size, Image.LANCZOS)
                left = (bg_img.width - W) // 2
                top = (bg_img.height - H) // 2
                bg_img = bg_img.crop((left, top, left + W, top + H))
                base = bg_img
            else:
                color_hex_clean = color_hex.lstrip('#') if color_hex else ''
                if len(color_hex_clean) not in (3,6):
                    return 'bad color', 400
                if len(color_hex_clean) == 3:
                    color_hex_clean = ''.join(c*2 for c in color_hex_clean)
                try:
                    r = int(color_hex_clean[0:2],16)
                    g = int(color_hex_clean[2:4],16)
                    bcol = int(color_hex_clean[4:6],16)
                except ValueError:
                    return 'bad color', 400
                from PIL import Image as PILImage
                base = PILImage.new('RGBA', (W,H), (r,g,bcol,255))
            base.alpha_composite(img)
            composed = base
        # text overlay
        if text:
            draw = ImageDraw.Draw(composed)
            tc = text_color_hex.lstrip('#')
            if len(tc) == 3:
                tc = ''.join(c*2 for c in tc)
            if len(tc) != 6:
                tc = '000000'
            try:
                tr = int(tc[0:2],16); tg = int(tc[2:4],16); tb = int(tc[4:6],16)
            except ValueError:
                tr, tg, tb = 0,0,0
            try:
                size_int = max(8, min(400, int(text_size)))
            except ValueError:
                size_int = 48
            font_obj = None
            if text_font:
                font_path = os.path.join('fonts', os.path.basename(text_font))
                if os.path.exists(font_path):
                    try:
                        font_obj = ImageFont.truetype(font_path, size_int)
                    except Exception:
                        font_obj = None
            if font_obj is None:
                try:
                    font_obj = ImageFont.truetype("DejaVuSans.ttf", size_int)
                except Exception:
                    font_obj = ImageFont.load_default()
            text_bbox = draw.textbbox((0,0), text, font=font_obj)
            tw = text_bbox[2]-text_bbox[0]
            th = text_bbox[3]-text_bbox[1]
            W,H = composed.size
            margin = 10
            pos_map = {
                'tl': (margin, margin), 'tc': ((W-tw)//2, margin), 'tr': (W - tw - margin, margin),
                'cl': (margin, (H-th)//2), 'cc': ((W-tw)//2, (H-th)//2), 'cr': (W - tw - margin, (H-th)//2),
                'bl': (margin, H - th - margin), 'bc': ((W-tw)//2, H - th - margin), 'br': (W - tw - margin, H - th - margin)
            }
            tx, ty = pos_map.get(text_pos, pos_map['bc'])
            offsets = [(0,0),(1,0),(0,1),(1,1)] if text_bold else [(0,0)]
            for ox, oy in offsets:
                draw.text((tx+ox, ty+oy), text, font=font_obj, fill=(tr,tg,tb,255))
        # flips
        if flip:
            if 'h' in flip:
                composed = composed.transpose(Image.FLIP_LEFT_RIGHT)
            if 'v' in flip:
                composed = composed.transpose(Image.FLIP_TOP_BOTTOM)
        # rotation
        try:
            rdeg = float(rotate)
        except ValueError:
            rdeg = 0
        if rdeg % 360 != 0:
            composed = composed.rotate(-rdeg, expand=True, resample=Image.BICUBIC)
        bio = io.BytesIO()
        composed.save(bio, format='PNG')
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
