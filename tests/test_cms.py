import io
import os
import re
import tempfile
import unittest
from pathlib import Path

os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='hydroflow-test-')
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['ADMIN_PASSWORD'] = 'test-password-12345'
from app import app, db
from PIL import Image

class CMS(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.get('/admin/login')
        self.post('/admin/login', {'username': 'admin', 'password': 'test-password-12345'})

    def post(self, path, data=None):
        with self.client.session_transaction() as session:
            if 'csrf' not in session:
                session['csrf'] = 'test-csrf-token'
            token = session['csrf']
        return self.client.post(path, data={'csrf': token, **(data or {})}, follow_redirects=False)

    def image(self):
        data=io.BytesIO()
        Image.new('RGB',(80,120),'teal').save(data,'PNG')
        data.seek(0)
        return data

    def test_auth_csrf_and_landing(self):
        stranger=app.test_client()
        self.assertEqual(stranger.get('/admin').status_code,302)
        self.assertEqual(stranger.post('/admin/contact').status_code,400)
        self.assertEqual(self.client.get('/admin').status_code,200)
        page=self.client.get('/').text
        self.assertIn('documentation-column',page)
        self.assertNotIn('{{',page)
        Path('/tmp/hydroflow-rendered.html').write_text(page)

    def test_contact_and_escaping(self):
        result=self.post('/admin/contact',{'phone':'+62 812 1234 5678','whatsapp':'+62 812 1234 5678','email':'test@example.com','message':'Halo & selamat datang'})
        self.assertEqual(result.status_code,302)
        page=self.client.get('/').text
        self.assertIn('https://wa.me/6281212345678?text=Halo%20%26%20selamat%20datang',page)
        self.assertIn('mailto:test@example.com',page)
        self.post('/admin/contact',{'phone':'bad','whatsapp':'javascript:bad','email':'bad','message':'bad'})
        self.assertIn('test@example.com',self.client.get('/').text)

    def test_photo_lifecycle_and_validation(self):
        self.post('/admin/photos/upload',{'photos':(self.image(),'project.png')})
        with app.app_context():
            photo=db().execute('SELECT * FROM photos ORDER BY id DESC').fetchone()
        self.assertTrue(photo['src'].endswith('.webp'))
        response=self.client.get(photo['src'])
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.mimetype,'image/webp')
        self.post(f'/admin/photos/{photo["id"]}',{'caption':'<script>alert(1)</script>','position':'0','visible':'on'})
        self.assertIn('&lt;script&gt;',self.client.get('/').text)
        self.post(f'/admin/photos/{photo["id"]}',{'caption':'hidden-photo-marker','position':'0'})
        self.assertNotIn('hidden-photo-marker',self.client.get('/').text)
        self.post(f'/admin/photos/{photo["id"]}',{'action':'delete'})
        self.assertEqual(self.client.get(photo['src']).status_code,404)
        with app.app_context():
            before=db().execute('SELECT COUNT(*) FROM photos').fetchone()[0]
        self.post('/admin/photos/upload',{'photos':(io.BytesIO(b'<svg onload="alert(1)"></svg>'),'evil.png')})
        with app.app_context():
            self.assertEqual(before,db().execute('SELECT COUNT(*) FROM photos').fetchone()[0])

    def test_logo_and_reset(self):
        self.post('/admin/logo',{'logo':(self.image(),'logo.png')})
        with app.app_context():
            src=db().execute("SELECT value FROM settings WHERE key='logo'").fetchone()[0]
        self.assertIn(src,self.client.get('/').text)
        self.post('/admin/logo',{'action':'reset'})
        self.assertEqual(self.client.get(src).status_code,404)
        self.assertIn('/logo-hsm.svg',self.client.get('/').text)

    def test_zero_photos(self):
        with app.app_context():
            db().execute('UPDATE photos SET visible=0'); db().commit()
        page=self.client.get('/').text
        self.assertNotIn('id="documentation-gallery"',page)
        self.assertIn('if (gallery)',page)
        with app.app_context():
            db().execute('UPDATE photos SET visible=1'); db().commit()

    def test_password_change(self):
        self.post('/admin/password',{'current_password':'test-password-12345','password':'new-password-12345','confirm_password':'new-password-12345'})
        self.post('/admin/logout')
        self.assertEqual(self.post('/admin/login',{'username':'admin','password':'test-password-12345'}).status_code,401)
        self.assertEqual(self.post('/admin/login',{'username':'admin','password':'new-password-12345'}).status_code,302)
        self.post('/admin/password',{'current_password':'new-password-12345','password':'test-password-12345','confirm_password':'test-password-12345'})

if __name__=='__main__':
    unittest.main(verbosity=2)
