import json
import os
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from urllib.robotparser import RobotFileParser

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='hydroflow-seo-test-'))
os.environ.setdefault('SECRET_KEY', 'seo-test-secret')
os.environ.setdefault('ADMIN_PASSWORD', 'test-password-12345')
from app import app, db, PUBLIC_SITE_URL

class SEO(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_public_metadata_and_structured_data(self):
        response = self.client.get('/?utm_source=test', headers={'Host': 'untrusted.example'})
        self.assertEqual(response.status_code, 200)
        page = response.text
        self.assertNotIn('noindex', response.headers.get('X-Robots-Tag', ''))
        self.assertIn(f'<link rel="canonical" href="{PUBLIC_SITE_URL}/">', page)
        self.assertNotIn('untrusted.example', page)
        self.assertEqual(len(re.findall(r'<h1\b', page)), 1)
        self.assertIn('Monitoring air berbasis IoT', page)
        self.assertIn('id="faq"', page)
        self.assertNotRegex(page, r'href=[\"\']/admin')
        self.assertIn('name="description"', page)
        self.assertIn('property="og:url"', page)
        self.assertIn('name="twitter:card"', page)
        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
        data = json.loads(match.group(1))
        self.assertEqual(data['@context'], 'https://schema.org')
        entities = {entity['@type']: entity for entity in data['@graph']}
        self.assertEqual(entities['WebSite']['name'], 'Hydroflow')
        self.assertEqual(entities['WebSite']['publisher']['@id'], entities['Organization']['@id'])
        self.assertEqual(entities['WebPage']['isPartOf']['@id'], entities['WebSite']['@id'])
        self.assertEqual(entities['WebPage']['about']['@id'], entities['Service']['@id'])
        with app.app_context():
            email = db().execute("SELECT value FROM settings WHERE key='email'").fetchone()[0]
        self.assertEqual(entities['Organization']['email'], email)
        self.assertNotIn('aggregateRating', match.group(1))

    def test_sitemap_and_robots_public_urls_only(self):
        response = self.client.get('/sitemap.xml', headers={'Host': 'untrusted.example'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/xml')
        root = ET.fromstring(response.data)
        locations = [node.text for node in root.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        self.assertEqual(locations, [PUBLIC_SITE_URL + '/'])
        self.assertNotIn('/admin', response.text)
        robots = self.client.get('/robots.txt')
        self.assertEqual(robots.mimetype, 'text/plain')
        parser = RobotFileParser()
        parser.parse(robots.text.splitlines())
        self.assertTrue(parser.can_fetch('Googlebot', PUBLIC_SITE_URL + '/'))
        # Crawlers must be able to read noindex on the public login page.
        self.assertTrue(parser.can_fetch('Googlebot', PUBLIC_SITE_URL + '/admin/login'))
        self.assertEqual(parser.site_maps(), [PUBLIC_SITE_URL + '/sitemap.xml'])

    def test_admin_redirect_login_errors_and_authenticated_page_are_noindex(self):
        for path in ('/admin', '/admin/', '/admin/login', '/admin/unknown'):
            response = self.client.get(path)
            self.assertIn('noindex', response.headers['X-Robots-Tag'], path)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        response = self.client.post('/admin/login', data={})
        self.assertEqual(response.status_code, 400)
        self.assertIn('noindex', response.headers['X-Robots-Tag'])
        login = self.client.get('/admin/login').text
        self.assertIn('name="robots" content="noindex,nofollow"', login)
        with app.app_context():
            user = db().execute('SELECT id, version FROM users LIMIT 1').fetchone()
        with self.client.session_transaction() as session:
            session['user'], session['version'] = user['id'], user['version']
        response = self.client.get('/admin')
        self.assertEqual(response.status_code, 200)
        self.assertIn('noindex', response.headers['X-Robots-Tag'])
        self.assertIn('name="robots" content="noindex,nofollow"', response.text)
        self.assertIn('noindex', self.client.get('/healthz').headers['X-Robots-Tag'])
        self.assertIn('noindex', self.client.get('/missing').headers['X-Robots-Tag'])
