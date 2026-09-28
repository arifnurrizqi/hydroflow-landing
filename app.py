import hmac
import os
import re
import secrets
import sqlite3
import time
import warnings
from datetime import timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import quote

from flask import Flask, abort, flash, g, redirect, render_template, request, send_from_directory, session, url_for
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).parent
DATA = Path(os.environ.get('DATA_DIR', ROOT / 'data'))
DATA.mkdir(parents=True, exist_ok=True)
UPLOADS = DATA / 'uploads'
UPLOADS.mkdir(exist_ok=True)
app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ['SECRET_KEY'], MAX_CONTENT_LENGTH=32 * 1024 * 1024,
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
Image.MAX_IMAGE_PIXELS = 25_000_000

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATA / 'cms.sqlite3', timeout=20)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    connection = g.pop('db', None)
    if connection:
        connection.close()

with app.app_context():
    db().executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS photos (id INTEGER PRIMARY KEY, src TEXT NOT NULL, caption TEXT NOT NULL DEFAULT '', position INTEGER NOT NULL DEFAULT 0, visible INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS attempts (ip TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL);
    ''')
    defaults = {'phone': '0899 8095 663', 'whatsapp': '628998095663', 'email': 'arnurtech@gmail.com',
                'message': 'Halo Arnur Tech, saya ingin berdiskusi tentang Hydroflow.', 'logo': '/logo-hsm.svg'}
    for key, value in defaults.items():
        db().execute('INSERT OR IGNORE INTO settings VALUES (?,?)', (key, value))
    if not db().execute('SELECT 1 FROM users').fetchone():
        password = os.environ.get('ADMIN_PASSWORD', '')
        if len(password) < 12:
            raise RuntimeError('Set ADMIN_PASSWORD to at least 12 characters for initial setup.')
        db().execute('INSERT INTO users(username,password) VALUES (?,?)', (os.environ.get('ADMIN_USERNAME', 'admin'), generate_password_hash(password)))
    if not db().execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
        for i in range(1, 10):
            db().execute('INSERT INTO photos(src,caption,position) VALUES (?,?,?)', (f'https://picsum.photos/seed/hydroflow-{i}/800/800', f'Foto placeholder {i}', i))
        db().execute("INSERT INTO settings VALUES ('seeded','1')")
    db().commit()

def settings():
    return dict(db().execute('SELECT key,value FROM settings').fetchall())

def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']
app.jinja_env.globals['csrf_token'] = csrf_token

@app.before_request
def protect_posts():
    if request.method == 'POST':
        supplied = request.form.get('csrf', '')
        if not supplied or not hmac.compare_digest(supplied, session.get('csrf', '')):
            abort(400, 'Form kedaluwarsa. Muat ulang halaman lalu coba lagi.')

@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if request.path.startswith('/admin'):
        response.headers['Cache-Control'] = 'no-store'
    return response

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = db().execute('SELECT * FROM users WHERE id=?', (session.get('user'),)).fetchone()
        if not user or session.get('version') != user['version']:
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped

@app.get('/')
def landing():
    config = settings()
    photos = db().execute('SELECT * FROM photos WHERE visible=1 ORDER BY position,id').fetchall()
    columns = []
    i = 0
    while i < len(photos):
        count = 1 if len(columns) % 3 == 0 else 2
        columns.append(photos[i:i+count])
        i += count
    return render_template('landing.html', config=config, columns=columns,
                           whatsapp_url='https://wa.me/' + config['whatsapp'] + '?text=' + quote(config['message']),
                           phone_href=re.sub(r'[^+0-9]', '', config['phone']))

@app.get('/logo-hsm.svg')
def original_logo():
    return send_from_directory(ROOT, 'logo-hsm.svg')

@app.get('/uploads/<name>')
def uploads(name):
    return send_from_directory(UPLOADS, name, max_age=86400)

@app.get('/healthz')
def health():
    db().execute('SELECT 1').fetchone()
    return {'status': 'ok'}

@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = request.remote_addr
        now = time.time()
        attempt = db().execute('SELECT * FROM attempts WHERE ip=?', (ip,)).fetchone()
        if attempt and now - attempt['started'] < 900 and attempt['count'] >= 10:
            return render_template('login.html', error='Terlalu banyak percobaan. Coba lagi dalam 15 menit.'), 429
        user = db().execute('SELECT * FROM users WHERE username=?', (request.form.get('username', ''),)).fetchone()
        if user and check_password_hash(user['password'], request.form.get('password', '')):
            session.clear()
            session.update(user=user['id'], version=user['version'])
            session.permanent = True
            db().execute('DELETE FROM attempts WHERE ip=?', (ip,))
            db().commit()
            return redirect(url_for('admin'))
        count = attempt['count'] + 1 if attempt and now - attempt['started'] < 900 else 1
        started = attempt['started'] if count > 1 else now
        db().execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?)', (ip, count, started))
        db().commit()
        return render_template('login.html', error='Username atau password salah.'), 401
    return render_template('login.html')

@app.get('/admin')
@app.get('/admin/')
@admin_required
def admin():
    return render_template('admin.html', config=settings(), photos=db().execute('SELECT * FROM photos ORDER BY position,id').fetchall())

@app.post('/admin/logout')
@admin_required
def logout():
    session.clear()
    return redirect(url_for('login'))

def save_image(file):
    if not file or not file.filename:
        raise ValueError('Pilih file gambar terlebih dahulu.')
    file.stream.seek(0, 2)
    if file.stream.tell() > 10 * 1024 * 1024:
        raise ValueError('Maksimal ukuran setiap gambar 10 MB.')
    file.stream.seek(0)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(file.stream) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ValueError('Gunakan gambar JPG, PNG, atau WebP.')
                img = ImageOps.exif_transpose(source)
                img.thumbnail((1920, 1920))
                img = img.convert('RGBA' if 'A' in img.getbands() or 'transparency' in img.info else 'RGB')
                name = secrets.token_hex(16) + '.webp'
                img.save(UPLOADS / name, 'WEBP', quality=85)
                return '/uploads/' + name
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('File gambar tidak valid atau dimensinya terlalu besar.')

def remove_image(src):
    if src.startswith('/uploads/'):
        (UPLOADS / Path(src).name).unlink(missing_ok=True)

@app.post('/admin/photos/upload')
@admin_required
def photo_upload():
    saved = []
    try:
        files = [f for f in request.files.getlist('photos') if f.filename]
        if not files:
            raise ValueError('Pilih minimal satu foto.')
        if len(files) > 20:
            raise ValueError('Upload maksimal 20 foto sekaligus.')
        for file in files:
            saved.append(save_image(file))
        position = db().execute('SELECT COALESCE(MAX(position),0) FROM photos').fetchone()[0]
        for i, src in enumerate(saved, 1):
            db().execute('INSERT INTO photos(src,position) VALUES (?,?)', (src, position + i))
        db().commit()
        flash(f'{len(saved)} foto berhasil ditambahkan.', 'success')
    except ValueError as exc:
        for src in saved:
            remove_image(src)
        flash(str(exc), 'error')
    return redirect(url_for('admin') + '#dokumentasi')

@app.post('/admin/photos/<int:photo_id>')
@admin_required
def photo_update(photo_id):
    photo = db().execute('SELECT * FROM photos WHERE id=?', (photo_id,)).fetchone()
    if not photo:
        abort(404)
    if request.form.get('action') == 'delete':
        db().execute('DELETE FROM photos WHERE id=?', (photo_id,))
        db().commit()
        remove_image(photo['src'])
        flash('Foto dihapus.', 'success')
    else:
        try:
            position = int(request.form.get('position', '0'))
            if not 0 <= position <= 1_000_000:
                raise ValueError()
        except ValueError:
            flash('Urutan harus berupa angka 0–1000000.', 'error')
            return redirect(url_for('admin') + '#dokumentasi')
        db().execute('UPDATE photos SET caption=?,position=?,visible=? WHERE id=?',
                     (request.form.get('caption', '')[:200], position, int('visible' in request.form), photo_id))
        db().commit()
        flash('Foto diperbarui.', 'success')
    return redirect(url_for('admin') + '#dokumentasi')

@app.post('/admin/contact')
@admin_required
def contact_update():
    values = {key: request.form.get(key, '').strip() for key in ('phone', 'whatsapp', 'email', 'message')}
    values['whatsapp'] = re.sub(r'[\s+()-]', '', values['whatsapp'])
    if not re.fullmatch(r'[0-9]{8,15}', values['whatsapp']) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', values['email']) or not re.fullmatch(r'[+0-9 ()-]{6,30}', values['phone']) or not 1 <= len(values['message']) <= 1000 or len(values['email']) > 254:
        flash('Periksa nomor telepon, WhatsApp (kode negara), email, dan pesan.', 'error')
    else:
        for key, value in values.items():
            db().execute('UPDATE settings SET value=? WHERE key=?', (value, key))
        db().commit()
        flash('Kontak berhasil disimpan.', 'success')
    return redirect(url_for('admin') + '#kontak')

@app.post('/admin/logo')
@admin_required
def logo_update():
    old = settings()['logo']
    try:
        src = '/logo-hsm.svg' if request.form.get('action') == 'reset' else save_image(request.files.get('logo'))
        db().execute("UPDATE settings SET value=? WHERE key='logo'", (src,))
        db().commit()
        if old != src:
            remove_image(old)
        flash('Logo berhasil diperbarui.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('admin') + '#logo')

@app.post('/admin/password')
@admin_required
def password_update():
    user = db().execute('SELECT * FROM users WHERE id=?', (session['user'],)).fetchone()
    password = request.form.get('password', '')
    if not check_password_hash(user['password'], request.form.get('current_password', '')):
        flash('Password saat ini salah.', 'error')
    elif len(password) < 12 or len(password) > 200 or password != request.form.get('confirm_password'):
        flash('Password baru harus 12–200 karakter dan konfirmasinya harus sama.', 'error')
    else:
        db().execute('UPDATE users SET password=?,version=version+1 WHERE id=?', (generate_password_hash(password), user['id']))
        db().commit()
        session['version'] = user['version'] + 1
        flash('Password berhasil diganti.', 'success')
    return redirect(url_for('admin') + '#akun')

@app.errorhandler(413)
def too_large(error):
    return render_template('error.html', message='Total upload maksimal 32 MB per pengiriman. Coba unggah dalam beberapa batch.'), 413

@app.errorhandler(400)
def bad_request(error):
    return render_template('error.html', message=error.description), 400
