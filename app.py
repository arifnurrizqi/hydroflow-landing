import hmac
import os
import re
import secrets
import sqlite3
import time
import warnings
from datetime import date, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import quote, urlsplit, parse_qs

from flask import Flask, Response, abort, flash, g, redirect, render_template, request, send_from_directory, session, url_for
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

ROOT = Path(__file__).parent
# Use a configured public origin, never an untrusted incoming Host header.
PUBLIC_SITE_URL = os.environ.get('PUBLIC_SITE_URL', 'https://hydroflow.arnur.id').rstrip('/')
_public_origin = urlsplit(PUBLIC_SITE_URL)
if (_public_origin.scheme != 'https' or not _public_origin.hostname or
        _public_origin.username or _public_origin.password or _public_origin.path or
        _public_origin.query or _public_origin.fragment):
    raise RuntimeError('PUBLIC_SITE_URL must be an HTTPS origin without a path.')
SEO_TITLE = 'Hydroflow | Monitoring Air IoT & Kualitas Air Realtime'
SEO_DESCRIPTION = ('Pantau penggunaan, kualitas, dan level air secara realtime dengan Hydroflow. '
                   'Satu dashboard IoT untuk banyak perangkat, alarm, dan histori data air.')
DATA = Path(os.environ.get('DATA_DIR', ROOT / 'data'))
DATA.mkdir(parents=True, exist_ok=True)
UPLOADS = DATA / 'uploads'
UPLOADS.mkdir(exist_ok=True)
RELEASE_FILES = DATA / 'releases'
RELEASE_FILES.mkdir(exist_ok=True)
app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ['SECRET_KEY'], MAX_CONTENT_LENGTH=16 * 1024 * 1024,
                  MAX_FORM_PARTS=40, MAX_FORM_MEMORY_SIZE=128 * 1024,
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
MAX_IMAGE_PIXELS = 12_500_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATA / 'cms.sqlite3', timeout=20)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
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
        CREATE TABLE IF NOT EXISTS releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL COLLATE NOCASE UNIQUE,
            title TEXT NOT NULL, released_on TEXT NOT NULL,
            summary TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published')),
            cover TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS releases_public_date ON releases(status, released_on DESC, id DESC);
        CREATE TABLE IF NOT EXISTS release_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
            filename TEXT NOT NULL, original_name TEXT NOT NULL,
            title TEXT NOT NULL, size INTEGER NOT NULL,
            is_public INTEGER NOT NULL DEFAULT 1 CHECK(is_public IN (0,1))
        );
        CREATE INDEX IF NOT EXISTS release_docs_parent ON release_documents(release_id);

    ''')
    defaults = {'phone': '0899 8095 663', 'whatsapp': '628998095663', 'email': 'arnurtech@gmail.com',
                'message': 'Halo Arnur Tech, saya ingin berdiskusi tentang Hydroflow.', 'logo': '/logo-hsm.svg', 'demo_video': ''}
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

def youtube_id(value):
    """Accept supported YouTube URLs and return only a validated video ID."""
    if len(value) > 2048:
        raise ValueError('Link video terlalu panjang.')
    try:
        url = urlsplit(value)
        if url.scheme not in {'http', 'https'} or url.username or url.password or url.port:
            raise ValueError()
        host = url.hostname
        parts = url.path.strip('/').split('/')
        video_id = ''
        if host == 'youtu.be' and len(parts) == 1:
            video_id = parts[0]
        elif host in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtube-nocookie.com', 'www.youtube-nocookie.com'}:
            if url.path == '/watch' and host in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
                video_id = parse_qs(url.query).get('v', [''])[0]
            elif len(parts) == 2 and parts[0] in {'embed', 'shorts', 'live'}:
                video_id = parts[1]
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            raise ValueError()
        return video_id
    except ValueError:
        raise ValueError('Masukkan link video YouTube yang valid (watch, youtu.be, Shorts, live, atau embed).') from None


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
    if request.path == '/' or request.path.startswith('/changelog'):
        response.headers['Cache-Control'] = 'no-store'
    if request.path.startswith('/admin'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    elif request.path == '/healthz' or response.status_code >= 400:
        response.headers['X-Robots-Tag'] = 'noindex'
    return response

def is_admin():
    user = db().execute('SELECT version FROM users WHERE id=?', (session.get('user'),)).fetchone()
    return bool(user and session.get('version') == user['version'])


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not is_admin():
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped

@app.get('/')
def landing():
    config = settings()
    demo_embed_url = ''
    if config['demo_video']:
        try:
            demo_embed_url = 'https://www.youtube-nocookie.com/embed/' + youtube_id(config['demo_video'])
        except ValueError:
            pass
    photos = db().execute('SELECT * FROM photos WHERE visible=1 ORDER BY position,id').fetchall()
    columns = []
    i = 0
    while i < len(photos):
        count = 1 if len(columns) % 3 == 0 else 2
        columns.append(photos[i:i+count])
        i += count
    canonical_url = PUBLIC_SITE_URL + '/'
    organization_id = canonical_url + '#organization'
    website_id = canonical_url + '#website'
    logo_url = PUBLIC_SITE_URL + config['logo']
    structured_data = {
        '@context': 'https://schema.org',
        '@graph': [
            {'@type': 'Organization', '@id': organization_id, 'name': 'Arnur Tech',
             'url': canonical_url, 'logo': logo_url, 'email': config['email'],
             'telephone': config['phone']},
            {'@type': 'WebSite', '@id': website_id, 'name': 'Hydroflow',
             'alternateName': 'Hydroflow by Arnur Tech', 'url': canonical_url,
             'inLanguage': 'id-ID', 'publisher': {'@id': organization_id}},
            {'@type': 'WebPage', '@id': canonical_url + '#webpage',
             'url': canonical_url, 'name': SEO_TITLE, 'description': SEO_DESCRIPTION,
             'inLanguage': 'id-ID', 'isPartOf': {'@id': website_id},
             'about': {'@id': canonical_url + '#service'}},
            {'@type': 'Service', '@id': canonical_url + '#service',
             'name': 'Hydroflow — Sistem Monitoring Air IoT', 'url': canonical_url,
             'serviceType': 'Monitoring penggunaan, kualitas, dan level air berbasis IoT',
             'description': SEO_DESCRIPTION, 'provider': {'@id': organization_id}}
        ]
    }
    return render_template('landing.html', config=config, columns=columns, demo_embed_url=demo_embed_url,
                           latest_releases=db().execute("SELECT * FROM releases WHERE status='published' ORDER BY released_on DESC,id DESC LIMIT 3").fetchall(),
                           seo_title=SEO_TITLE, seo_description=SEO_DESCRIPTION,
                           canonical_url=canonical_url, structured_data=structured_data,
                           social_image=logo_url if config['logo'].startswith('/uploads/') else '',
                           whatsapp_url='https://wa.me/' + config['whatsapp'] + '?text=' + quote(config['message']),
                           phone_href=re.sub(r'[^+0-9]', '', config['phone']))

@app.get('/robots.txt')
def robots():
    # Admin stays crawlable so search engines can read its noindex directive.
    # Authentication still protects all management content and operations.
    return Response('User-agent: *\nAllow: /\n\nSitemap: ' + PUBLIC_SITE_URL + '/sitemap.xml\n',
                    mimetype='text/plain', headers={'Cache-Control': 'public, max-age=3600'})

@app.get('/sitemap.xml')
def sitemap():
    return Response(render_template('sitemap.xml', canonical_url=PUBLIC_SITE_URL + '/',
                    published_releases=db().execute("SELECT id FROM releases WHERE status='published' ORDER BY released_on DESC,id DESC").fetchall()),
                    mimetype='application/xml', headers={'Cache-Control': 'public, max-age=3600'})


@app.get('/google195041c754aa4836.html')
def google_site_verification():
    # Serve only the uploaded verification file; never expose the project root.
    return send_from_directory(ROOT, 'google195041c754aa4836.html', mimetype='text/html')


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
                # Check the header before decoding. Compressed file size does not
                # bound decoded pixel memory, especially for PNG and WebP.
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ValueError('Dimensi foto maksimal 12,5 megapiksel. Perkecil gambar terlebih dahulu.')
                # Resize before EXIF rotation to avoid two full-resolution copies.
                # thumbnail also uses JPEG draft decoding where supported.
                source.thumbnail((1920, 1920))
                with ImageOps.exif_transpose(source) as oriented:
                    mode = 'RGBA' if 'A' in oriented.getbands() or 'transparency' in oriented.info else 'RGB'
                    with oriented.convert(mode) as img:
                        name = secrets.token_hex(16) + '.webp'
                        img.save(UPLOADS / name, 'WEBP', quality=82, method=2)
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
        if len(files) > 8:
            raise ValueError('Upload maksimal 8 foto sekaligus.')
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

@app.post('/admin/video')
@admin_required
def video_update():
    value = request.form.get('demo_video', '').strip()
    try:
        canonical = 'https://www.youtube.com/watch?v=' + youtube_id(value) if value else ''
        db().execute("UPDATE settings SET value=? WHERE key='demo_video'", (canonical,))
        db().commit()
        flash('Video demo berhasil disimpan.' if canonical else 'Video demo disembunyikan.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('admin') + '#video-demo')

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
    return render_template('error.html', message='Total upload maksimal 16 MB per pengiriman. Coba unggah dalam beberapa batch.'), 413

@app.errorhandler(400)
def bad_request(error):
    return render_template('error.html', message=error.description), 400

# Release media is deliberately kept outside the publicly served uploads folder.
def get_release(release_id):
    row = db().execute('SELECT * FROM releases WHERE id=?', (release_id,)).fetchone()
    if not row:
        abort(404)
    return row


def release_page_number():
    try:
        page = int(request.args.get('page', '1'))
        if not 1 <= page <= 100000:
            raise ValueError()
        return page
    except ValueError:
        abort(404)


def release_metadata():
    values = {key: request.form.get(key, '').strip() for key in
              ('version', 'title', 'released_on', 'summary', 'notes', 'status')}
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+\-]{0,39}', values['version']):
        raise ValueError('Nomor versi maksimal 40 karakter, gunakan huruf, angka, titik, +, - atau _.')
    if not 1 <= len(values['title']) <= 120 or not 1 <= len(values['summary']) <= 600 or len(values['notes']) > 12000:
        raise ValueError('Isi judul (maks. 120), ringkasan (maks. 600), dan catatan (maks. 12000 karakter).')
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', values['released_on']):
            raise ValueError()
        date.fromisoformat(values['released_on'])
    except ValueError:
        raise ValueError('Tanggal rilis tidak valid.') from None
    if values['status'] not in {'draft', 'published'}:
        raise ValueError('Pilih status draft atau dipublikasikan.')
    return values


def save_release_cover(file):
    src = save_image(file)
    name = Path(src).name
    try:
        (UPLOADS / name).replace(RELEASE_FILES / name)
    except OSError:
        remove_image(src)
        raise
    return name


def delete_release_file(name):
    if name:
        (RELEASE_FILES / Path(name).name).unlink(missing_ok=True)


@app.get('/admin/versions')
@admin_required
def admin_versions():
    page = release_page_number()
    count = db().execute('SELECT COUNT(*) FROM releases').fetchone()[0]
    pages = max(1, (count + 19) // 20)
    if page > pages:
        abort(404)
    releases = db().execute('SELECT * FROM releases ORDER BY released_on DESC,id DESC LIMIT 20 OFFSET ?', ((page - 1) * 20,)).fetchall()
    return render_template('admin_versions.html', releases=releases, page=page, pages=pages, count=count)


@app.route('/admin/versions/new', methods=['GET', 'POST'])
@app.route('/admin/versions/<int:release_id>', methods=['GET', 'POST'])
@admin_required
def edit_release(release_id=None):
    current = get_release(release_id) if release_id else None
    values = dict(current) if current else {'version': '', 'title': '', 'summary': '', 'notes': '',
                                          'released_on': date.today().isoformat(), 'status': 'draft', 'cover': ''}
    error = None
    if request.method == 'POST':
        new_cover = ''
        try:
            values.update(release_metadata())
            cover_file = request.files.get('cover')
            if cover_file and cover_file.filename:
                new_cover = save_release_cover(cover_file)
            cover = new_cover or ('' if 'remove_cover' in request.form else values['cover'])
            args = tuple(values[key] for key in ('version','title','released_on','summary','notes','status')) + (cover,)
            if current:
                db().execute('UPDATE releases SET version=?,title=?,released_on=?,summary=?,notes=?,status=?,cover=? WHERE id=?', args + (release_id,))
            else:
                release_id = db().execute('INSERT INTO releases(version,title,released_on,summary,notes,status,cover) VALUES (?,?,?,?,?,?,?)', args).lastrowid
            db().commit()
            if current and current['cover'] and current['cover'] != cover:
                delete_release_file(current['cover'])
            flash('Versi berhasil disimpan. Tambahkan manual book atau report di bagian lampiran.', 'success')
            return redirect(url_for('edit_release', release_id=release_id))
        except (ValueError, sqlite3.IntegrityError) as exc:
            db().rollback()
            delete_release_file(new_cover)
            error = 'Nomor versi sudah digunakan.' if isinstance(exc, sqlite3.IntegrityError) else str(exc)
            # Preserve entered text when a form fails validation.
            values.update({key: request.form.get(key, '') for key in ('version','title','released_on','summary','notes','status')})
    documents = db().execute('SELECT * FROM release_documents WHERE release_id=? ORDER BY id', (release_id,)).fetchall() if current else []
    return render_template('release_editor.html', release=values, release_id=release_id, documents=documents, error=error), 400 if error else 200


@app.post('/admin/versions/<int:release_id>/delete')
@admin_required
def delete_release(release_id):
    release = get_release(release_id)
    files = [r['filename'] for r in db().execute('SELECT filename FROM release_documents WHERE release_id=?', (release_id,))]
    db().execute('DELETE FROM releases WHERE id=?', (release_id,))
    db().commit()
    for name in files + [release['cover']]:
        delete_release_file(name)
    flash('Versi dan seluruh lampirannya dihapus.', 'success')
    return redirect(url_for('admin_versions'))


@app.post('/admin/versions/<int:release_id>/documents')
@admin_required
def upload_release_document(release_id):
    get_release(release_id)
    name = ''
    try:
        file = request.files.get('document')
        title = request.form.get('title', '').strip()
        if not 1 <= len(title) <= 160:
            raise ValueError('Isi nama dokumen, maksimal 160 karakter.')
        if not file or not file.filename or not file.filename.lower().endswith('.pdf'):
            raise ValueError('Pilih dokumen PDF.')
        file.stream.seek(0, 2)
        size = file.stream.tell()
        if not 1 <= size <= 10 * 1024 * 1024:
            raise ValueError('Ukuran PDF maksimal 10 MB.')
        file.stream.seek(0)
        if not file.stream.read(8).startswith(b'%PDF-'):
            raise ValueError('File bukan dokumen PDF yang valid.')
        file.stream.seek(max(0, size - 1024))
        if b'%%EOF' not in file.stream.read(1024):
            raise ValueError('Dokumen PDF tidak lengkap atau rusak.')
        file.stream.seek(0)
        db().execute('BEGIN IMMEDIATE')
        if db().execute('SELECT COUNT(*) FROM release_documents WHERE release_id=?', (release_id,)).fetchone()[0] >= 3:
            raise ValueError('Maksimal 3 PDF per versi. Hapus salah satu untuk menggantinya.')
        name = secrets.token_hex(16) + '.pdf'
        file.save(RELEASE_FILES / name)
        original = secure_filename(file.filename)[:140] or 'dokumen.pdf'
        if not original.lower().endswith('.pdf'):
            original += '.pdf'
        db().execute('INSERT INTO release_documents(release_id,filename,original_name,title,size,is_public) VALUES (?,?,?,?,?,?)',
                     (release_id, name, original, title, size, int('is_public' in request.form)))
        db().commit()
        flash('PDF berhasil ditambahkan.', 'success')
    except (ValueError, OSError) as exc:
        db().rollback()
        delete_release_file(name)
        flash(str(exc) if isinstance(exc, ValueError) else 'PDF tidak dapat disimpan. Periksa ruang penyimpanan.', 'error')
    return redirect(url_for('edit_release', release_id=release_id) + '#lampiran')


@app.post('/admin/versions/<int:release_id>/documents/<int:document_id>')
@admin_required
def update_release_document(release_id, document_id):
    document = db().execute('SELECT * FROM release_documents WHERE id=? AND release_id=?', (document_id, release_id)).fetchone()
    if not document:
        abort(404)
    if request.form.get('action') == 'delete':
        db().execute('DELETE FROM release_documents WHERE id=?', (document_id,))
        db().commit()
        delete_release_file(document['filename'])
        flash('PDF dihapus.', 'success')
    else:
        title = request.form.get('title', '').strip()
        if not 1 <= len(title) <= 160:
            flash('Nama dokumen harus 1–160 karakter.', 'error')
        else:
            db().execute('UPDATE release_documents SET title=?,is_public=? WHERE id=?', (title, int('is_public' in request.form), document_id))
            db().commit()
            flash('Informasi dokumen diperbarui.', 'success')
    return redirect(url_for('edit_release', release_id=release_id) + '#lampiran')


@app.get('/changelog')
def changelog():
    page = release_page_number()
    count = db().execute("SELECT COUNT(*) FROM releases WHERE status='published'").fetchone()[0]
    pages = max(1, (count + 9) // 10)
    if page > pages:
        abort(404)
    releases = db().execute("SELECT * FROM releases WHERE status='published' ORDER BY released_on DESC,id DESC LIMIT 10 OFFSET ?", ((page-1)*10,)).fetchall()
    response = app.make_response(render_template('changelog.html', config=settings(), releases=releases,
                                page=page, pages=pages, title='Riwayat Versi Hydroflow | Pembaruan & Manual Alat',
                                description='Riwayat pembaruan Hydroflow, foto alat, catatan rilis, serta manual book dan report yang dipublikasikan.',
                                canonical=PUBLIC_SITE_URL + '/changelog' + (f'?page={page}' if page > 1 else ''), noindex=not count))
    response.headers['Cache-Control'] = 'no-store'
    if not count:
        response.headers['X-Robots-Tag'] = 'noindex'
    return response


def render_release(release, preview=False):
    sql = 'SELECT * FROM release_documents WHERE release_id=?'
    if not preview:
        sql += ' AND is_public=1'
    documents = db().execute(sql + ' ORDER BY id', (release['id'],)).fetchall()
    response = app.make_response(render_template('release_detail.html', config=settings(), release=release, documents=documents,
                                preview=preview, noindex=preview, title=f"Hydroflow {release['version']} — {release['title']}",
                                description=release['summary'][:160], canonical=PUBLIC_SITE_URL + '/changelog/' + str(release['id'])))
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/changelog/<int:release_id>')
def release_detail(release_id):
    release = get_release(release_id)
    if release['status'] != 'published':
        abort(404)
    return render_release(release)


@app.get('/admin/versions/<int:release_id>/preview')
@admin_required
def preview_release(release_id):
    return render_release(get_release(release_id), preview=True)


@app.get('/changelog/<int:release_id>/cover')
def release_cover(release_id):
    release = get_release(release_id)
    private = release['status'] != 'published'
    if not release['cover'] or (private and not is_admin()):
        abort(404)
    response = send_from_directory(RELEASE_FILES, release['cover'], mimetype='image/webp')
    response.headers['Cache-Control'] = 'no-store'
    if private:
        response.headers['X-Robots-Tag'] = 'noindex'
    return response


@app.get('/changelog/documents/<int:document_id>')
def release_document(document_id):
    doc = db().execute('SELECT d.*,r.status FROM release_documents d JOIN releases r ON r.id=d.release_id WHERE d.id=?', (document_id,)).fetchone()
    if not doc:
        abort(404)
    private = not doc['is_public'] or doc['status'] != 'published'
    if private and not is_admin():
        abort(404)
    response = send_from_directory(RELEASE_FILES, doc['filename'], mimetype='application/pdf',
                                   download_name=doc['original_name'], as_attachment=request.args.get('download') == '1')
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "sandbox; default-src 'none'"
    if private:
        response.headers['X-Robots-Tag'] = 'noindex'
    return response
