import os
import io
from flask import Flask, request, render_template, send_file, url_for, jsonify, redirect, flash
from werkzeug.utils import secure_filename
from rembg import remove
from PIL import Image, ImageFont, ImageDraw
from zipfile import ZipFile
import math
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

UPLOAD_FOLDER = 'uploads'
RESULT_FOLDER = 'results'
BACKGROUND_FOLDER = 'backgrounds'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)
os.makedirs(BACKGROUND_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULT_FOLDER'] = RESULT_FOLDER
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', '')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', '1') == '1'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@example.com')
app.config['MAIL_SUPPRESS_SEND'] = False if app.config['MAIL_SERVER'] and app.config['MAIL_USERNAME'] else True

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

oauth = OAuth(app)
mail = Mail(app)
ts = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# --- OAuth Provider Configuration (safe to leave unconfigured) ---
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    try:
        oauth.register(
            name='google',
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'}
        )
    except Exception as _e:
        pass

FACEBOOK_CLIENT_ID = os.environ.get('FACEBOOK_CLIENT_ID')
FACEBOOK_CLIENT_SECRET = os.environ.get('FACEBOOK_CLIENT_SECRET')
if FACEBOOK_CLIENT_ID and FACEBOOK_CLIENT_SECRET:
    try:
        oauth.register(
            name='facebook',
            client_id=FACEBOOK_CLIENT_ID,
            client_secret=FACEBOOK_CLIENT_SECRET,
            access_token_url='https://graph.facebook.com/oauth/access_token',
            authorize_url='https://www.facebook.com/dialog/oauth',
            api_base_url='https://graph.facebook.com/',
            client_kwargs={'scope': 'email', 'token_placement': 'header'}
        )
    except Exception:
        pass

LINKEDIN_CLIENT_ID = os.environ.get('LINKEDIN_CLIENT_ID')
LINKEDIN_CLIENT_SECRET = os.environ.get('LINKEDIN_CLIENT_SECRET')
if LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET:
    try:
        oauth.register(
            name='linkedin',
            client_id=LINKEDIN_CLIENT_ID,
            client_secret=LINKEDIN_CLIENT_SECRET,
            access_token_url='https://www.linkedin.com/oauth/v2/accessToken',
            authorize_url='https://www.linkedin.com/oauth/v2/authorization',
            api_base_url='https://api.linkedin.com/v2/',
            client_kwargs={'scope': 'r_liteprofile r_emailaddress'}
        )
    except Exception:
        pass
@login_manager.user_loader
def load_user(user_id: str):
    if not user_id:
        return None
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None
@app.route('/pdf-converter/editor', methods=['GET','POST'])
def pdf_editor():
    if request.method == 'GET':
        return render_template('pdf_editor.html')
    from pypdf import PdfReader, PdfWriter
    f = request.files.get('pdf')
    if not f or not f.filename.lower().endswith('.pdf'):
        return render_template('pdf_editor.html', error='Please upload a PDF file')
    try:
        data = f.read()
        reader = PdfReader(io.BytesIO(data))
        total = len(reader.pages)
    except Exception as e:
        return render_template('pdf_editor.html', error=f'Unable to read PDF: {e}')
    order_csv = (request.form.get('order') or '').strip()
    indexes = []
    if order_csv:
        seen = set()
        for part in [p.strip() for p in order_csv.split(',') if p.strip()]:
            try:
                one_based = int(part)
            except ValueError:
                continue
            if one_based < 1 or one_based > total:
                continue
            zero_based = one_based - 1
            if zero_based in seen:
                continue
            seen.add(zero_based)
            indexes.append(zero_based)
    if not indexes:
        indexes = list(range(total))
    writer = PdfWriter()
    try:
        for idx in indexes:
            writer.add_page(reader.pages[idx])
        out_buf = io.BytesIO()
        writer.write(out_buf)
        out_buf.seek(0)
        base = os.path.splitext(secure_filename(f.filename))[0]
        return send_file(out_buf, mimetype='application/pdf', download_name=f'{base}_edited.pdf', as_attachment=True)
    except Exception as e:
        return render_template('pdf_editor.html', error=f'Edit failed: {e}')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            next_url = request.args.get('next')
            return redirect(next_url or url_for('index'))
        flash('Invalid email or password', 'error')
    return render_template('login.html',
                           google_enabled=bool(GOOGLE_CLIENT_ID),
                           facebook_enabled=bool(FACEBOOK_CLIENT_ID),
                           linkedin_enabled=bool(LINKEDIN_CLIENT_ID))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.before_request
def require_verified():
    if not current_user.is_authenticated:
        return
    # allow these endpoints without verification
    allowed = {
        'logout', 'verify_notice', 'verify_send', 'verify_token', 'register',
        'static', 'index', 'pdf_converter', 'image_upscale', 'image_editor',
        'pdf_split', 'pdf_merge', 'pdf_rotate', 'word_to_pdf', 'pdf_to_word', 'pdf_editor'
    }
    if request.endpoint in allowed:
        return
    if not getattr(current_user, 'email_verified', False):
        return redirect(url_for('verify_notice'))


@app.route('/forgot', methods=['GET','POST'])
def forgot_password():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                token = _token_for(email, 'reset')
                link = url_for('reset_password', token=token, _external=True)
                _send_email('Reset your password', [email], f"Reset your password: {link}\nIf you did not request this, ignore this email.")
        flash('If that email is registered, a reset link has been sent.', 'info')
    return render_template('forgot.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        name = (request.form.get('name') or '').strip()
        pw = request.form.get('password') or ''
        if not email or '@' not in email:
            flash('Enter a valid email', 'error')
            return render_template('register.html')
        if len(pw) < 6:
            flash('Password must be at least 6 characters', 'error')
            return render_template('register.html')
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('Email already registered', 'error')
            return render_template('register.html')
        user = User(email=email, name=name or None, email_verified=False)
        user.set_password(pw)
        db.session.add(user)
        db.session.commit()
        flash('Account created. Please verify your email.', 'info')
        login_user(user)
        return redirect(url_for('verify_notice'))
    return render_template('register.html')


@app.route('/reset/<token>', methods=['GET','POST'])
def reset_password(token):
    email = _verify_token(token, max_age=3600, purpose='reset')
    if not email:
        flash('Invalid or expired link', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        pw = request.form.get('password') or ''
        if len(pw) < 6:
            flash('Password must be at least 6 characters', 'error')
        else:
            user = User.query.filter_by(email=email).first()
            if user:
                user.set_password(pw)
                db.session.commit()
                flash('Password updated. Please log in.', 'info')
                return redirect(url_for('login'))
    return render_template('reset.html', token=token)


@app.route('/verify')
@login_required
def verify_notice():
    if current_user.email_verified:
        return redirect(url_for('index'))
    return render_template('verify_notice.html')


@app.route('/verify/send')
@login_required
def verify_send():
    token = _token_for(current_user.email, 'verify')
    link = url_for('verify_token', token=token, _external=True)
    _send_email('Verify your email', [current_user.email], f"Verify by clicking: {link}")
    flash('Verification email sent.', 'info')
    return redirect(url_for('verify_notice'))


@app.route('/verify/<token>')
def verify_token(token):
    email = _verify_token(token, max_age=86400, purpose='verify')
    if not email:
        flash('Invalid or expired link', 'error')
        return redirect(url_for('login'))
    user = User.query.filter_by(email=email).first()
    if user:
        user.email_verified = True
        db.session.commit()
        flash('Email verified!', 'info')
        login_user(user)
        return redirect(url_for('index'))
    flash('Account not found', 'error')
    return redirect(url_for('login'))


@app.context_processor
def inject_oauth_flags():
    return {
        'google_enabled': bool(GOOGLE_CLIENT_ID),
        'facebook_enabled': bool(FACEBOOK_CLIENT_ID),
        'linkedin_enabled': bool(LINKEDIN_CLIENT_ID),
        'is_authenticated': bool(getattr(current_user, 'is_authenticated', False)),
    }


@app.route('/login/google')
def login_google():
    if not GOOGLE_CLIENT_ID:
        flash('Google login not configured', 'error')
        return redirect(url_for('login'))
    redirect_uri = url_for('auth_google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/login/facebook')
def login_facebook():
    if not FACEBOOK_CLIENT_ID:
        flash('Facebook login not configured', 'error')
        return redirect(url_for('login'))
    redirect_uri = url_for('auth_facebook_callback', _external=True)
    return oauth.facebook.authorize_redirect(redirect_uri)


@app.route('/auth/facebook/callback')
def auth_facebook_callback():
    if not FACEBOOK_CLIENT_ID:
        return redirect(url_for('login'))
    token = oauth.facebook.authorize_access_token()
    # Fetch email and name
    me = oauth.facebook.get('me?fields=id,name,email').json()
    sub = me.get('id')
    email = (me.get('email') or f"fb_{sub}@facebook.local").lower()
    name = me.get('name') or ''
    user = User.query.filter((User.oauth_provider=='facebook') & (User.oauth_sub==sub)).first()
    if not user:
        user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, name=name, oauth_provider='facebook', oauth_sub=sub, email_verified=True)
        db.session.add(user)
    else:
        user.oauth_provider = 'facebook'
        user.oauth_sub = sub
        if not user.name:
            user.name = name
        user.email_verified = True
    db.session.commit()
    login_user(user)
    return redirect(url_for('index'))


@app.route('/login/linkedin')
def login_linkedin():
    if not LINKEDIN_CLIENT_ID:
        flash('LinkedIn login not configured', 'error')
        return redirect(url_for('login'))
    redirect_uri = url_for('auth_linkedin_callback', _external=True)
    return oauth.linkedin.authorize_redirect(redirect_uri)


@app.route('/auth/linkedin/callback')
def auth_linkedin_callback():
    if not LINKEDIN_CLIENT_ID:
        return redirect(url_for('login'))
    token = oauth.linkedin.authorize_access_token()
    # Fetch profile and email
    prof = oauth.linkedin.get('me').json()
    email_resp = oauth.linkedin.get('emailAddress?q=members&projection=(elements*(handle~))').json()
    sub = prof.get('id')
    elements = email_resp.get('elements') or []
    email = None
    if elements:
        primary = elements[0].get('handle~', {})
        email = primary.get('emailAddress')
    email = (email or f"li_{sub}@linkedin.local").lower()
    name = prof.get('localizedFirstName', '') + ' ' + prof.get('localizedLastName', '')
    user = User.query.filter((User.oauth_provider=='linkedin') & (User.oauth_sub==sub)).first()
    if not user:
        user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, name=name.strip(), oauth_provider='linkedin', oauth_sub=sub, email_verified=True)
        db.session.add(user)
    else:
        user.oauth_provider = 'linkedin'
        user.oauth_sub = sub
        if not user.name:
            user.name = name.strip()
        user.email_verified = True
    db.session.commit()
    login_user(user)
    return redirect(url_for('index'))


@app.route('/auth/google/callback')
def auth_google_callback():
    if not GOOGLE_CLIENT_ID:
        return redirect(url_for('login'))
    token = oauth.google.authorize_access_token()
    userinfo = token.get('userinfo')
    if not userinfo:
        # Fallback fetch
        userinfo = oauth.google.parse_id_token(token)
    sub = userinfo.get('sub')
    email = (userinfo.get('email') or '').lower()
    name = userinfo.get('name') or ''
    if not email:
        flash('Google account has no email', 'error')
        return redirect(url_for('login'))
    user = User.query.filter((User.oauth_provider=='google') & (User.oauth_sub==sub)).first()
    if not user:
        user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, name=name, oauth_provider='google', oauth_sub=sub)
        db.session.add(user)
    else:
        user.oauth_provider = 'google'
        user.oauth_sub = sub
        if not user.name:
            user.name = name
    db.session.commit()
    login_user(user)
    return redirect(url_for('index'))

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files.get('image')
        if file and file.filename:
            safe_name = secure_filename(file.filename)
            if not safe_name:
                flash('Invalid file name', 'error')
                return render_template('index.html')
            input_path = os.path.join(UPLOAD_FOLDER, safe_name)
            file.save(input_path)
            with open(input_path, 'rb') as inp:
                output = remove(inp.read())
            output_img = Image.open(io.BytesIO(output))
            output_path = os.path.join(RESULT_FOLDER, safe_name + '.png')
            output_img.save(output_path)
            result_filename = safe_name + '.png'
            preview_img = url_for('result_file', filename=result_filename)
            download_link = url_for('result_file', filename=result_filename)
            original_img = url_for('uploaded_file', filename=safe_name)
            return render_template('index.html',
                                   original_img=original_img,
                                   preview_img=preview_img,
                                   download_link=download_link,
                                   result_filename=result_filename)
        else:
            flash('Please choose an image to upload', 'error')
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
@login_required
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
    text_rotate = request.args.get('text_rotate', '0')  # rotation of text block only
    # absolute position overrides (pixels from top-left)
    text_x_arg = request.args.get('text_x')
    text_y_arg = request.args.get('text_y')
    text_box_w_arg = request.args.get('text_box_w')  # width constraint for wrapping
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
            # wrapping logic if box width provided or newlines
            W,H = composed.size
            max_wrap_w = None
            if text_box_w_arg:
                try:
                    max_wrap_w = int(float(text_box_w_arg))
                    if max_wrap_w < 20:
                        max_wrap_w = 20
                    if max_wrap_w > W:
                        max_wrap_w = W
                except ValueError:
                    max_wrap_w = None

            def wrap_lines(raw_text):
                if not max_wrap_w:
                    return raw_text.split('\n')
                lines = []
                for para in raw_text.split('\n'):
                    words = para.split(' ')
                    current = ''
                    for w in words:
                        candidate = w if current == '' else current + ' ' + w
                        bb = draw.textbbox((0,0), candidate, font=font_obj)
                        width_c = bb[2]-bb[0]
                        if width_c <= max_wrap_w:
                            current = candidate
                        else:
                            if current:
                                lines.append(current)
                            # word longer than box: hard break
                            bbw = draw.textbbox((0,0), w, font=font_obj)[2]
                            if bbw <= max_wrap_w:
                                current = w
                            else:
                                # break w into chars
                                acc = ''
                                for ch in w:
                                    test = acc + ch
                                    bb2 = draw.textbbox((0,0), test, font=font_obj)
                                    if (bb2[2]-bb2[0]) <= max_wrap_w:
                                        acc = test
                                    else:
                                        if acc:
                                            lines.append(acc)
                                        acc = ch
                                current = acc
                    if current:
                        lines.append(current)
                return lines

            lines = wrap_lines(text)
            # measure total block
            line_metrics = [draw.textbbox((0,0), ln, font=font_obj) for ln in lines]
            line_heights = [m[3]-m[1] for m in line_metrics]
            tw = max((m[2]-m[0]) for m in line_metrics) if line_metrics else 0
            th = sum(line_heights)
            margin = 10
            pos_map = {
                'tl': (margin, margin), 'tc': ((W-tw)//2, margin), 'tr': (W - tw - margin, margin),
                'cl': (margin, (H-th)//2), 'cc': ((W-tw)//2, (H-th)//2), 'cr': (W - tw - margin, (H-th)//2),
                'bl': (margin, H - th - margin), 'bc': ((W-tw)//2, H - th - margin), 'br': (W - tw - margin, H - th - margin)
            }
            # Determine coordinates
            use_abs = False
            tx = ty = 0
            if text_x_arg is not None and text_y_arg is not None:
                try:
                    tx = int(float(text_x_arg))
                    ty = int(float(text_y_arg))
                    use_abs = True
                except ValueError:
                    use_abs = False
            if not use_abs:
                tx, ty = pos_map.get(text_pos, pos_map['bc'])
            # Clamp to canvas so text stays fully visible
            tx = max(0, min(W - tw, tx))
            ty = max(0, min(H - th, ty))
            # Draw text either directly or on temp layer for rotation
            try:
                t_rotate = float(text_rotate)
            except ValueError:
                t_rotate = 0.0
            if t_rotate % 360 != 0:
                # render to separate transparent image then rotate and paste centered on original intended block
                from PIL import Image as PILImage
                temp = PILImage.new('RGBA', (tw, th), (0,0,0,0))
                tdraw = ImageDraw.Draw(temp)
                offsets = [(0,0),(1,0),(0,1),(1,1)] if text_bold else [(0,0)]
                cy_local = 0
                for idx, ln in enumerate(lines):
                    lh = line_heights[idx]
                    for ox, oy in offsets:
                        tdraw.text((ox, cy_local+oy), ln, font=font_obj, fill=(tr,tg,tb,255))
                    cy_local += lh
                rotated = temp.rotate(-t_rotate, expand=True, resample=Image.BICUBIC)
                # compute new top-left so center remains (tx,ty) block area center
                cx = tx + tw/2
                cy_center = ty + th/2
                new_left = int(cx - rotated.width/2)
                new_top = int(cy_center - rotated.height/2)
                composed.alpha_composite(rotated, (new_left, new_top))
            else:
                offsets = [(0,0),(1,0),(0,1),(1,1)] if text_bold else [(0,0)]
                for ox, oy in offsets:
                    cy = ty
                    for idx, ln in enumerate(lines):
                        draw.text((tx+ox, cy+oy), ln, font=font_obj, fill=(tr,tg,tb,255))
                        cy += line_heights[idx]
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

@app.route('/multi_resize')
@login_required
def multi_resize():
    """Generate multiple social-media sized variants (maintain aspect ratio, pad transparent) and return a zip."""
    from PIL import ImageEnhance
    fname = request.args.get('file')
    if not fname or '/' in fname or '..' in fname:
        return 'bad file', 400
    base_path = os.path.join(RESULT_FOLDER, fname)
    if not os.path.exists(base_path):
        return 'not found', 404
    # parse common params (duplicated from render_image for simplicity)
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
    text_rotate = request.args.get('text_rotate', '0')
    text_x_arg = request.args.get('text_x')
    text_y_arg = request.args.get('text_y')
    text_box_w_arg = request.args.get('text_box_w')
    rotate = request.args.get('rotate', '0')
    flip = request.args.get('flip', '')
    sizes_param = request.args.get('sizes', '')
    mode = request.args.get('mode', 'fit')  # fit or cover
    pad_hex = request.args.get('pad')  # optional hex for padding
    if not sizes_param:
        return 'no sizes', 400
    requested_sizes = [sname.strip() for sname in sizes_param.split(',') if sname.strip()]
    size_map = {
        'ig_square': (1080,1080,'ig_square'),
        'ig_portrait': (1080,1350,'ig_portrait'),
        'ig_landscape': (1080,566,'ig_landscape'),
        'fb_post': (1200,630,'fb_post'),
        'li_post': (1200,627,'li_post'),
        'x_post': (1600,900,'x_post'),
    }
    valid_specs = [size_map[k] for k in requested_sizes if k in size_map]
    if not valid_specs:
        return 'no valid sizes', 400
    try:
        # Reuse render logic to build composed image first
        img = Image.open(base_path).convert('RGBA')
        if b != 1:
            from PIL import ImageEnhance
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
                base_img = bg_img
            else:
                color_hex_clean = color_hex.lstrip('#') if color_hex else ''
                if len(color_hex_clean) == 3:
                    color_hex_clean = ''.join(c*2 for c in color_hex_clean)
                try:
                    r = int(color_hex_clean[0:2],16)
                    g = int(color_hex_clean[2:4],16)
                    bcol = int(color_hex_clean[4:6],16)
                except Exception:
                    r,g,bcol = 255,255,255
                base_img = Image.new('RGBA', img.size, (r,g,bcol,255))
            base_img.alpha_composite(img)
            composed = base_img
        # text (reuse from render_image simplified: copy-paste block for consistency)
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
                tr,tg,tb = 0,0,0
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
            W,H = composed.size
            max_wrap_w = None
            if text_box_w_arg:
                try:
                    max_wrap_w = int(float(text_box_w_arg))
                    if max_wrap_w < 20: max_wrap_w = 20
                    if max_wrap_w > W: max_wrap_w = W
                except ValueError:
                    max_wrap_w = None
            def wrap_lines(raw_text):
                if not max_wrap_w:
                    return raw_text.split('\n')
                lines = []
                for para in raw_text.split('\n'):
                    words = para.split(' ')
                    current = ''
                    for w in words:
                        candidate = w if current == '' else current + ' ' + w
                        bb = draw.textbbox((0,0), candidate, font=font_obj)
                        if (bb[2]-bb[0]) <= max_wrap_w:
                            current = candidate
                        else:
                            if current:
                                lines.append(current)
                            bbw = draw.textbbox((0,0), w, font=font_obj)[2]
                            if bbw <= max_wrap_w:
                                current = w
                            else:
                                acc = ''
                                for ch in w:
                                    test = acc + ch
                                    bb2 = draw.textbbox((0,0), test, font=font_obj)
                                    if (bb2[2]-bb2[0]) <= max_wrap_w:
                                        acc = test
                                    else:
                                        if acc:
                                            lines.append(acc)
                                        acc = ch
                                current = acc
                    if current:
                        lines.append(current)
                return lines
            lines = wrap_lines(text)
            line_metrics = [draw.textbbox((0,0), ln, font=font_obj) for ln in lines]
            line_heights = [m[3]-m[1] for m in line_metrics]
            tw = max((m[2]-m[0]) for m in line_metrics) if line_metrics else 0
            th = sum(line_heights)
            margin = 10
            pos_map = {
                'tl': (margin, margin), 'tc': ((W-tw)//2, margin), 'tr': (W - tw - margin, margin),
                'cl': (margin, (H-th)//2), 'cc': ((W-tw)//2, (H-th)//2), 'cr': (W - tw - margin, (H-th)//2),
                'bl': (margin, H - th - margin), 'bc': ((W-tw)//2, H - th - margin), 'br': (W - tw - margin, H - th - margin)
            }
            use_abs = False
            tx = ty = 0
            if text_x_arg is not None and text_y_arg is not None:
                try:
                    tx = int(float(text_x_arg)); ty = int(float(text_y_arg)); use_abs = True
                except ValueError:
                    use_abs = False
            if not use_abs:
                tx, ty = pos_map.get(text_pos, pos_map['bc'])
            tx = max(0, min(W - tw, tx))
            ty = max(0, min(H - th, ty))
            try:
                t_rotate = float(text_rotate)
            except ValueError:
                t_rotate = 0.0
            offsets_base = [(0,0),(1,0),(0,1),(1,1)] if text_bold else [(0,0)]
            if t_rotate % 360 != 0:
                temp = Image.new('RGBA', (tw, th), (0,0,0,0))
                tdraw = ImageDraw.Draw(temp)
                cy_local = 0
                for idx, ln in enumerate(lines):
                    lh = line_heights[idx]
                    for ox, oy in offsets_base:
                        tdraw.text((ox, cy_local+oy), ln, font=font_obj, fill=(tr,tg,tb,255))
                    cy_local += lh
                rotated = temp.rotate(-t_rotate, expand=True, resample=Image.BICUBIC)
                cx = tx + tw/2; cyc = ty + th/2
                new_left = int(cx - rotated.width/2); new_top = int(cyc - rotated.height/2)
                composed.alpha_composite(rotated, (new_left, new_top))
            else:
                for ox, oy in offsets_base:
                    cy_draw = ty
                    for idx, ln in enumerate(lines):
                        draw.text((tx+ox, cy_draw+oy), ln, font=font_obj, fill=(tr,tg,tb,255))
                        cy_draw += line_heights[idx]
        # flips & rotation (global)
        if flip:
            if 'h' in flip:
                composed = composed.transpose(Image.FLIP_LEFT_RIGHT)
            if 'v' in flip:
                composed = composed.transpose(Image.FLIP_TOP_BOTTOM)
        try:
            rdeg = float(rotate)
        except ValueError:
            rdeg = 0
        if rdeg % 360 != 0:
            composed = composed.rotate(-rdeg, expand=True, resample=Image.BICUBIC)
        # build variants
        baseW, baseH = composed.size
        zip_buffer = io.BytesIO()
        with ZipFile(zip_buffer, 'w') as zf:
            for (tW, tH, tag) in valid_specs:
                if mode == 'cover':
                    scale = max(tW / baseW, tH / baseH)
                else:  # fit
                    scale = min(tW / baseW, tH / baseH)
                new_size = (int(baseW * scale), int(baseH * scale))
                resized = composed.resize(new_size, Image.LANCZOS)
                if mode == 'cover':
                    # center crop to target
                    left = (new_size[0] - tW) // 2 if new_size[0] > tW else 0
                    top = (new_size[1] - tH) // 2 if new_size[1] > tH else 0
                    crop_box = (left, top, left + tW, top + tH)
                    cropped = resized.crop(crop_box)
                    canvas = cropped.copy()
                else:
                    if pad_hex and len(pad_hex) in (3,6):
                        ph = pad_hex.lstrip('#')
                        if len(ph) == 3: ph = ''.join(c*2 for c in ph)
                        try:
                            pr = int(ph[0:2],16); pg = int(ph[2:4],16); pb = int(ph[4:6],16)
                        except Exception:
                            pr,pg,pb = 0,0,0
                        canvas = Image.new('RGBA', (tW, tH), (pr,pg,pb,255))
                    else:
                        canvas = Image.new('RGBA', (tW, tH), (0,0,0,0))
                    off_x = (tW - new_size[0]) // 2
                    off_y = (tH - new_size[1]) // 2
                    canvas.alpha_composite(resized, (off_x, off_y))
                out_bytes = io.BytesIO()
                canvas.save(out_bytes, format='PNG')
                out_bytes.seek(0)
                base_name = os.path.splitext(os.path.basename(fname))[0]
                zf.writestr(f"{base_name}_{tag}.png", out_bytes.read())
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', download_name='resized_variants.zip', as_attachment=True)
    except Exception as e:
        return f'error {e}', 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename))

@app.route('/results/<filename>')
def result_file(filename):
    return send_file(os.path.join(RESULT_FOLDER, filename))

# Simple placeholder routes for menu items
@app.route('/pdf-converter')
def pdf_converter():
    return render_template('pdf_converter.html')

@app.route('/image-upscale')
def image_upscale():
    return render_template('image_upscale.html')

@app.route('/image-editor')
def image_editor():
    return render_template('image_editor.html')

# PDF sub-tools
@app.route('/pdf-converter/split', methods=['GET','POST'])
def pdf_split():
    if request.method == 'GET':
        return render_template('pdf_split.html')
    # POST: perform split
    from pypdf import PdfReader, PdfWriter
    import re
    f = request.files.get('pdf')
    if not f or not f.filename.lower().endswith('.pdf'):
        return render_template('pdf_split.html', error='Please upload a PDF file')
    try:
        data = f.read()
        reader = PdfReader(io.BytesIO(data))
    except Exception as e:
        return render_template('pdf_split.html', error=f'Unable to read PDF: {e}')
    mode = request.form.get('mode','each')
    zip_buf = io.BytesIO()
    with ZipFile(zip_buf, 'w') as zf:
        base = os.path.splitext(secure_filename(f.filename))[0]
        if mode == 'each':
            for i, page in enumerate(reader.pages):
                writer = PdfWriter()
                writer.add_page(page)
                out_io = io.BytesIO()
                writer.write(out_io)
                out_io.seek(0)
                zf.writestr(f"{base}_p{i+1}.pdf", out_io.read())
        else:
            # ranges mode
            raw = (request.form.get('ranges') or '').strip()
            if not raw:
                return render_template('pdf_split.html', error='Enter ranges like 1-3,5,7-9')
            # parse ranges
            parts = [p.strip() for p in raw.split(',') if p.strip()]
            ranges = []
            for p in parts:
                m = re.match(r'^(\d+)(?:-(\d+))?$', p)
                if not m:
                    return render_template('pdf_split.html', error=f'Bad range: {p}')
                a = int(m.group(1)); b = int(m.group(2) or a)
                if a > b:
                    a, b = b, a
                ranges.append((a,b))
            total = len(reader.pages)
            for idx,(a,b) in enumerate(ranges, start=1):
                # convert 1-based to 0-based and clamp
                start = max(0, min(total-1, a-1))
                end = max(0, min(total-1, b-1))
                writer = PdfWriter()
                for j in range(start, end+1):
                    writer.add_page(reader.pages[j])
                out_io = io.BytesIO()
                writer.write(out_io)
                out_io.seek(0)
                zf.writestr(f"{base}_part{idx}_{a}-{b}.pdf", out_io.read())
    zip_buf.seek(0)
    return send_file(zip_buf, mimetype='application/zip', download_name='pdf_split.zip', as_attachment=True)

@app.route('/pdf-converter/merge', methods=['GET','POST'])
def pdf_merge():
    if request.method == 'GET':
        return render_template('pdf_merge.html')
    # POST: perform merge
    from pypdf import PdfReader, PdfWriter
    files = request.files.getlist('pdfs') or []
    # filter only PDFs and with a filename
    valid = [(secure_filename(f.filename), f) for f in files if f and f.filename and f.filename.lower().endswith('.pdf')]
    if len(valid) < 2:
        return render_template('pdf_merge.html', error='Please upload at least two PDF files')
    sort_by_name = request.form.get('sort_name') == '1'
    try:
        if sort_by_name:
            valid.sort(key=lambda t: t[0].lower())
        writer = PdfWriter()
        for safe_name, f in valid:
            try:
                data = f.read()
                reader = PdfReader(io.BytesIO(data))
                for page in reader.pages:
                    writer.add_page(page)
            except Exception as e:
                return render_template('pdf_merge.html', error=f'Failed to read {safe_name}: {e}')
        out_buf = io.BytesIO()
        writer.write(out_buf)
        out_buf.seek(0)
        # Build a base name from first file
        base = os.path.splitext(valid[0][0])[0] if valid else 'merged'
        return send_file(out_buf, mimetype='application/pdf', download_name=f'{base}_merged.pdf', as_attachment=True)
    except Exception as e:
        return render_template('pdf_merge.html', error=f'Unexpected error: {e}')

@app.route('/pdf-converter/rotate', methods=['GET','POST'])
def pdf_rotate():
    if request.method == 'GET':
        return render_template('pdf_rotate.html')
    from pypdf import PdfReader, PdfWriter
    import re
    f = request.files.get('pdf')
    if not f or not f.filename.lower().endswith('.pdf'):
        return render_template('pdf_rotate.html', error='Please upload a PDF file')
    angle_preset = request.form.get('angle_preset', '90')
    if angle_preset == 'custom':
        try:
            angle = int(float(request.form.get('angle_custom', '0')))
        except ValueError:
            return render_template('pdf_rotate.html', error='Custom angle must be a number')
    else:
        try:
            angle = int(angle_preset)
        except ValueError:
            angle = 90
    # Normalize angle to one of allowed values by modulo 360
    angle = angle % 360
    # pypdf PageObject supports rotate_clockwise with multiples of 90 only; enforce
    if angle % 90 != 0:
        return render_template('pdf_rotate.html', error='Angle must be a multiple of 90° for reliable rotation')
    scope = request.form.get('scope', 'all')
    ranges_raw = (request.form.get('ranges') or '').strip()
    try:
        data = f.read()
        reader = PdfReader(io.BytesIO(data))
    except Exception as e:
        return render_template('pdf_rotate.html', error=f'Unable to read PDF: {e}')
    total = len(reader.pages)
    indices_to_rotate = set(range(total))
    if scope == 'ranges':
        if not ranges_raw:
            return render_template('pdf_rotate.html', error='Specify ranges like 1-3,5,7-9')
        parts = [p.strip() for p in ranges_raw.split(',') if p.strip()]
        selected = set()
        for p in parts:
            m = re.match(r'^(\d+)(?:-(\d+))?$', p)
            if not m:
                return render_template('pdf_rotate.html', error=f'Bad range: {p}')
            a = int(m.group(1)); b = int(m.group(2) or a)
            if a > b:
                a, b = b, a
            # convert to 0-based
            a0 = max(0, min(total-1, a-1))
            b0 = max(0, min(total-1, b-1))
            for i in range(a0, b0+1):
                selected.add(i)
        indices_to_rotate = selected
    writer = PdfWriter()
    try:
        for i, page in enumerate(reader.pages):
            pg = page
            if i in indices_to_rotate:
                # rotate clockwise by given angle
                pg.rotate(angle)
            writer.add_page(pg)
        out = io.BytesIO()
        writer.write(out)
        out.seek(0)
        base = os.path.splitext(secure_filename(f.filename))[0]
        return send_file(out, mimetype='application/pdf', download_name=f'{base}_rotated.pdf', as_attachment=True)
    except Exception as e:
        return render_template('pdf_rotate.html', error=f'Rotation failed: {e}')

@app.route('/pdf-converter/word-to-pdf', methods=['GET','POST'])
def word_to_pdf():
    if request.method == 'GET':
        return render_template('word_to_pdf.html')
    # POST: convert Word to PDF using LibreOffice headless
    f = request.files.get('doc')
    if not f or not f.filename:
        return render_template('word_to_pdf.html', error='Please choose a .docx or .doc file')
    lower = f.filename.lower()
    if not (lower.endswith('.docx') or lower.endswith('.doc')):
        return render_template('word_to_pdf.html', error='Unsupported file type. Please upload .docx or .doc')
    import shutil, subprocess, tempfile, glob
    # discover libreoffice/soffice
    soffice = shutil.which('soffice') or shutil.which('libreoffice')
    if not soffice:
        return render_template('word_to_pdf.html', error='LibreOffice is not installed on the server. On Ubuntu/Debian, run: sudo apt-get update && sudo apt-get install -y libreoffice')
    base_safe = secure_filename(f.filename)
    if not base_safe:
        base_safe = 'document.docx'
    base_no_ext = os.path.splitext(base_safe)[0]
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, base_safe)
            f.save(in_path)
            # Run LibreOffice headless conversion
            cmd = [soffice, '--headless', '--convert-to', 'pdf', '--outdir', tmpdir, in_path]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
            # LibreOffice may still succeed with non-zero in some cases; check for output file existence
            out_path = os.path.join(tmpdir, base_no_ext + '.pdf')
            if not os.path.exists(out_path):
                # Fallback: any PDF in tmpdir
                pdfs = glob.glob(os.path.join(tmpdir, '*.pdf'))
                if pdfs:
                    out_path = pdfs[0]
            if not os.path.exists(out_path):
                err = (proc.stderr or proc.stdout or '').strip()
                if len(err) > 500:
                    err = err[-500:]
                return render_template('word_to_pdf.html', error=f'Conversion failed. Details: {err or "no output produced"}')
            with open(out_path, 'rb') as rf:
                data = rf.read()
            bio = io.BytesIO(data)
            bio.seek(0)
            return send_file(bio, mimetype='application/pdf', download_name=f'{base_no_ext}.pdf', as_attachment=True)
    except subprocess.TimeoutExpired:
        return render_template('word_to_pdf.html', error='Conversion timed out. Try a smaller file or simpler document.')
    except Exception as e:
        return render_template('word_to_pdf.html', error=f'Unexpected error: {e}')

@app.route('/pdf-converter/pdf-to-word')
def pdf_to_word():
    return render_template('pdf_to_word.html')


if __name__ == '__main__':
    app.run(debug=True)
