from flask import Flask, session, redirect, url_for
from urllib.parse import quote_plus
from extensions import db
import os

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

if os.environ.get('MYSQLHOST'):
    DB_USER = os.environ['MYSQLUSER']
    DB_PASS = os.environ['MYSQLPASSWORD']
    DB_HOST = os.environ['MYSQLHOST']
    DB_PORT = os.environ.get('MYSQLPORT', '3306')
    DB_NAME = os.environ['MYSQLDATABASE']
else:
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASS = os.environ.get('DB_PASS')
    if not DB_PASS:
        raise RuntimeError(
            'Neither MYSQLHOST (Railway) nor DB_PASS (.env) is set. '
            'Create a .env file (see .env.example) for local dev.'
        )
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '3306')
    DB_NAME = os.environ.get('DB_NAME', 'jewellery_orders')

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASS)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)

from routes.main import main_bp
from routes.orders import orders_bp
from routes.admin import admin_bp
from routes.customers import customers_bp
from routes.vendors import vendors_bp
from routes.reports import reports_bp

app.register_blueprint(main_bp)
app.register_blueprint(orders_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(customers_bp)
app.register_blueprint(vendors_bp)
app.register_blueprint(reports_bp)

import json as _json

@app.template_filter('from_json')
def from_json_filter(value):
    if not value or value.strip() in ('', '[]', 'null'):
        return []
    try:
        result = _json.loads(value)
        return result if isinstance(result, list) and result else []
    except Exception:
        return []

@app.template_filter('get_images')
def get_images_filter(order):
    imgs = from_json_filter(order.reference_images)
    if not imgs and order.reference_image:
        imgs = [order.reference_image]
    return imgs

@app.template_filter('img_url')
def img_url_filter(key):
    if not key:
        return ''
    if key.startswith('http://') or key.startswith('https://'):
        return key
    from utils.storage import get_signed_url
    return get_signed_url(key)

with app.app_context():
    db.create_all()
    from sqlalchemy import text
    with db.engine.connect() as conn:
        for col, definition in [
            ('order_no', 'VARCHAR(100)'),
            ('reference_images', 'TEXT'),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE `order` ADD COLUMN `{col}` {definition}"))
                conn.commit()
            except Exception:
                pass

# ── Sync API ───────────────────────────────────────────────────────────────────
import base64 as _b64, hashlib as _hs
from flask import request as _req

@app.route('/api/export', methods=['GET'])
def api_export():
    """Pull endpoint — returns encrypted cloud snapshot to local sync.py"""
    secret = os.environ.get('SYNC_SECRET', '')
    if not secret:
        return _json.dumps({'ok': False, 'error': 'SYNC_SECRET not set'}), 500

    provided = _req.headers.get('X-Sync-Key', '')
    expected = _hs.sha256(secret.encode()).hexdigest()
    if provided != expected:
        return _json.dumps({'ok': False, 'error': 'Unauthorized'}), 401

    try:
        from sqlalchemy import text, inspect
        from cryptography.fernet import Fernet
        import base64 as _b64e

        snapshot = {'exported_at': str(db.session.execute(text('SELECT NOW()')).scalar())}
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        with db.engine.connect() as conn:
            for tbl in tables:
                if tbl == 'last_sync':
                    continue
                rows = conn.execute(text(f'SELECT * FROM `{tbl}`')).mappings().all()
                snapshot[tbl] = [dict(r) for r in rows]

        fkey      = _b64e.urlsafe_b64encode(_hs.sha256(secret.encode()).digest())
        encrypted = Fernet(fkey).encrypt(_json.dumps(snapshot, default=str).encode())
        return encrypted, 200, {'Content-Type': 'application/octet-stream'}

    except Exception as e:
        import traceback
        return _json.dumps({'ok': False, 'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/sync', methods=['POST'])
def api_sync():
    """Push endpoint — receives encrypted snapshot from local sync.py"""
    secret = os.environ.get('SYNC_SECRET', '')
    if not secret:
        return _json.dumps({'ok': False, 'error': 'SYNC_SECRET not set on Railway'}), 500

    provided = _req.headers.get('X-Sync-Key', '')
    expected = _hs.sha256(secret.encode()).hexdigest()
    if provided != expected:
        return _json.dumps({'ok': False, 'error': 'Unauthorized'}), 401

    try:
        from cryptography.fernet import Fernet
        raw  = _req.get_data()
        fkey = _b64.urlsafe_b64encode(_hs.sha256(secret.encode()).digest())
        data = _json.loads(Fernet(fkey).decrypt(raw).decode())
        _import_snapshot(data)
        return _json.dumps({'ok': True, 'exported_at': data.get('exported_at')})
    except Exception as e:
        import traceback
        return _json.dumps({'ok': False, 'error': str(e), 'trace': traceback.format_exc()}), 500


def _import_snapshot(data):
    from sqlalchemy import text

    FK_ORDER = [
        'branches', 'users', 'vendors', 'products',
        'customers', 'orders', 'order_status_logs',
    ]
    all_tables = [k for k in data if k != 'exported_at']
    all_tables.sort(key=lambda t: FK_ORDER.index(t) if t in FK_ORDER else len(FK_ORDER))

    with db.engine.begin() as conn:
        conn.execute(text('SET FOREIGN_KEY_CHECKS=0'))
        for tbl in reversed(all_tables):
            try:
                conn.execute(text(f'DELETE FROM `{tbl}`'))
            except Exception:
                pass
        conn.execute(text('SET FOREIGN_KEY_CHECKS=1'))

        for tbl in all_tables:
            rows = data.get(tbl, [])
            if not rows:
                continue
            col_list = list(rows[0].keys())
            cols = ', '.join(f'`{c}`' for c in col_list)
            ph   = ', '.join([':' + c for c in col_list])
            sql  = text(f'INSERT IGNORE INTO `{tbl}` ({cols}) VALUES ({ph})')
            for row in rows:
                try:
                    conn.execute(sql, {c: row.get(c) for c in col_list})
                except Exception:
                    pass

        try:
            conn.execute(text(
                'CREATE TABLE IF NOT EXISTS last_sync '
                '(id INT PRIMARY KEY, synced_at DATETIME)'
            ))
            conn.execute(text(
                'INSERT INTO last_sync (id,synced_at) VALUES (1,NOW()) '
                'ON DUPLICATE KEY UPDATE synced_at=NOW()'
            ))
        except Exception:
            pass


if __name__ == '__main__':
    app.run(debug=True, port=5000)
