import io
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='hydroflow-release-test-'))
os.environ.setdefault('SECRET_KEY', 'release-test-secret')
os.environ.setdefault('ADMIN_PASSWORD', 'test-password-12345')
from app import app, db, RELEASE_FILES, PUBLIC_SITE_URL
from PIL import Image

# A tiny one-page PDF fixture; no PDF renderer or generator dependency required.
PDF = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n'

class Releases(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.visitor = app.test_client()
        with app.app_context():
            user = db().execute('SELECT id,version FROM users LIMIT 1').fetchone()
        with self.client.session_transaction() as session:
            session.update(user=user['id'], version=user['version'], csrf='release-test-csrf')

    def tearDown(self):
        with app.app_context():
            rows = db().execute('SELECT id FROM releases').fetchall()
        for row in rows:
            self.post(f'/admin/versions/{row["id"]}/delete')

    def post(self, path, data=None):
        return self.client.post(path, data={'csrf':'release-test-csrf', **(data or {})})

    def values(self, **changes):
        return {'version':'v1.0.0', 'title':'Alat generasi pertama', 'released_on':'2026-09-29',
                'summary':'Ringkasan alat Hydroflow.', 'notes':'Fitur baru\n• Pembacaan sensor', 'status':'draft', **changes}

    def picture(self):
        data=io.BytesIO()
        with Image.new('RGB',(80,120),'teal') as image:
            image.save(data,'PNG')
        data.seek(0)
        return data

    def create(self, **changes):
        response = self.post('/admin/versions/new', self.values(**changes))
        self.assertEqual(response.status_code,302)
        return int(response.headers['Location'].rstrip('/').split('/')[-1])

    def add_pdf(self, release_id, **changes):
        return self.post(f'/admin/versions/{release_id}/documents', {'title':'Manual book', 'document':(io.BytesIO(PDF),'manual.pdf'), 'is_public':'on', **changes})

    def documents(self, release_id):
        with app.app_context():
            return db().execute('SELECT * FROM release_documents WHERE release_id=? ORDER BY id',(release_id,)).fetchall()

    def test_draft_media_private_publish_and_unpublish(self):
        release_id=self.create(cover=(self.picture(),'cover.png'))
        self.add_pdf(release_id)
        doc=self.documents(release_id)[0]
        detail=f'/changelog/{release_id}'
        cover=detail+'/cover'
        pdf=f'/changelog/documents/{doc["id"]}'
        for path in (detail,cover,pdf):
            self.assertEqual(self.visitor.get(path).status_code,404)
        self.assertNotIn('Alat generasi pertama',self.visitor.get('/').text)
        self.assertEqual(self.client.get(f'/admin/versions/{release_id}/preview').status_code,200)
        self.assertIn('noindex',self.client.get(f'/admin/versions/{release_id}/preview').headers['X-Robots-Tag'])
        for path in (cover,pdf):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn('noindex',response.headers['X-Robots-Tag'])
            response.close()
        self.post(f'/admin/versions/{release_id}',self.values(status='published'))
        self.assertIn('Alat generasi pertama',self.visitor.get('/').text)
        self.assertIn('Manual book',self.visitor.get(detail).text)
        response=self.visitor.get(pdf+'?download=1')
        self.assertEqual(response.data,PDF)
        self.assertIn('attachment;',response.headers['Content-Disposition'])
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        response.close()
        response=self.visitor.get(pdf,headers={'Range':'bytes=0-7'})
        self.assertEqual(response.status_code,206)
        self.assertEqual(response.data,PDF[:8]); response.close()
        self.post(f'/admin/versions/{release_id}',self.values(status='draft'))
        for path in (detail,cover,pdf):
            self.assertEqual(self.visitor.get(path).status_code,404)

    def test_private_document_and_path_not_exposed(self):
        rid=self.create(status='published',cover=(self.picture(),'cover.png'))
        self.add_pdf(rid)
        doc=self.documents(rid)[0]
        self.post(f'/admin/versions/{rid}/documents/{doc["id"]}',{'title':'Internal report','action':'save'})
        path=f'/changelog/documents/{doc["id"]}'
        self.assertEqual(self.visitor.get(path).status_code,404)
        self.assertNotIn('Internal report',self.visitor.get(f'/changelog/{rid}').text)
        response=self.client.get(path); self.assertEqual(response.status_code,200); response.close()
        self.assertEqual(self.visitor.get('/uploads/'+doc['filename']).status_code,404)
        with app.app_context():
            name=db().execute('SELECT cover FROM releases WHERE id=?',(rid,)).fetchone()[0]
        self.assertEqual(self.visitor.get('/uploads/'+name).status_code,404)
        self.post(f'/admin/versions/{rid}/documents/{doc["id"]}',{'title':'Public report','action':'save','is_public':'on'})
        response=self.visitor.get(path); self.assertEqual(response.status_code,200); response.close()

    def test_pdf_limits_and_file_cleanup(self):
        rid=self.create()
        for i in range(4):
            self.add_pdf(rid,title=f'Manual {i}')
        self.assertEqual(len(self.documents(rid)),3)
        first=self.documents(rid)[0]
        self.post(f'/admin/versions/{rid}/documents/{first["id"]}',{'action':'delete'})
        self.assertFalse((RELEASE_FILES/first['filename']).exists())
        before=set(RELEASE_FILES.iterdir())
        for content,name in [(b'<html>not pdf</html>','bad.pdf'),(PDF,'bad.html'),(b'%PDF-1.4\nbroken','bad.pdf'),(b'%PDF-1.4\n'+b'x'*(10*1024*1024)+b'%%EOF','large.pdf')]:
            self.post(f'/admin/versions/{rid}/documents',{'title':'Invalid','document':(io.BytesIO(content),name)})
        self.assertEqual(len(self.documents(rid)),2)
        self.assertEqual(set(RELEASE_FILES.iterdir()),before)
        files=[doc['filename'] for doc in self.documents(rid)]
        self.post(f'/admin/versions/{rid}/delete')
        self.assertEqual(self.documents(rid),[])
        self.assertTrue(all(not (RELEASE_FILES/name).exists() for name in files))

    def test_validation_and_authentication(self):
        for data in [self.values(version='bad version'), self.values(released_on='2026-02-30'),self.values(status='bad'),self.values(summary='')]:
            self.assertEqual(self.post('/admin/versions/new',data).status_code,400)
        rid=self.create()
        self.assertEqual(self.post('/admin/versions/new',self.values()).status_code,400)
        self.assertEqual(self.visitor.get('/admin/versions').status_code,302)
        self.assertEqual(self.visitor.post('/admin/versions/new').status_code,400)
        with self.visitor.session_transaction() as session:
            session['csrf']='visitor-token'
        response=self.visitor.post(f'/admin/versions/{rid}/delete',data={'csrf':'visitor-token'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get(f'/admin/versions/{rid}').status_code,200)

    def test_three_latest_sitemap_and_pagination(self):
        ids=[]
        for i in range(12):
            ids.append(self.create(version=f'v{i}',title=f'RELEASE-{i}-MARKER',released_on=f'2026-09-{i+1:02d}',status='published'))
        draft=self.create(version='private-v99',title='DRAFT-MARKER')
        page=self.visitor.get('/').text
        for i in (9,10,11): self.assertIn(f'RELEASE-{i}-MARKER',page)
        self.assertNotIn('RELEASE-8-MARKER',page)
        self.assertNotIn('DRAFT-MARKER',page)
        self.assertIn('RELEASE-11-MARKER',self.visitor.get('/changelog').text)
        self.assertNotIn('RELEASE-0-MARKER',self.visitor.get('/changelog').text)
        self.assertIn('RELEASE-0-MARKER',self.visitor.get('/changelog?page=2').text)
        self.assertEqual(self.visitor.get('/changelog?page=99').status_code,404)
        root=ET.fromstring(self.visitor.get('/sitemap.xml').data)
        urls=[node.text for node in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        self.assertIn(PUBLIC_SITE_URL+'/changelog',urls)
        self.assertIn(PUBLIC_SITE_URL+f'/changelog/{ids[-1]}',urls)
        self.assertNotIn(PUBLIC_SITE_URL+f'/changelog/{draft}',urls)

    def test_cover_replacement_and_escaped_notes(self):
        rid=self.create(cover=(self.picture(),'first.png'),status='published',notes='<script>alert(1)</script>')
        with app.app_context():
            old=db().execute('SELECT cover FROM releases WHERE id=?',(rid,)).fetchone()[0]
        self.assertIn('&lt;script&gt;',self.visitor.get(f'/changelog/{rid}').text)
        self.post(f'/admin/versions/{rid}',self.values(cover=(self.picture(),'new.png'),status='published'))
        self.assertFalse((RELEASE_FILES/old).exists())
        with app.app_context():
            new=db().execute('SELECT cover FROM releases WHERE id=?',(rid,)).fetchone()[0]
        self.assertNotEqual(old,new)
        self.post(f'/admin/versions/{rid}',self.values(remove_cover='on'))
        self.assertFalse((RELEASE_FILES/new).exists())
        self.assertEqual(self.client.get(f'/changelog/{rid}/cover').status_code,404)
