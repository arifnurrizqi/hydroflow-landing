"""Run the development CMS locally with persistent, generated credentials."""
import json
import os
import secrets
from pathlib import Path


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    data = root / 'data' / 'local'
    data.mkdir(parents=True, exist_ok=True)
    config_path = data / 'credentials.json'
    if not config_path.exists():
        config_path.write_text(json.dumps({
            'SECRET_KEY': secrets.token_urlsafe(48),
            'ADMIN_USERNAME': 'admin',
            'ADMIN_PASSWORD': secrets.token_urlsafe(18),
        }, indent=2), encoding='utf-8')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    os.environ.update(config)
    os.environ['DATA_DIR'] = str(data)
    from app import app

    print(f'Local login credentials: {config_path}', flush=True)
    app.run(host='127.0.0.1', port=8091, debug=False, use_reloader=False)
