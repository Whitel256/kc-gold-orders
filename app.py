from flask import Flask, session, redirect, url_for
from urllib.parse import quote_plus
from extensions import db
import os

app = Flask(__name__)

# Load from environment, fall back to dev defaults
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

# Railway's native MySQL plugin variable names (proven working pattern --
# matches the working sync setup in the SIVION/gold_dealer project).
# We build the connection string ourselves from these individual pieces
# rather than trusting Railway's combined MYSQL_URL reference, which can
# fail to resolve correctly depending on how the variable reference was
# set up.
if os.environ.get('MYSQLHOST'):
    DB_USER = os.environ['MYSQLUSER']
    DB_PASS = os.environ['MYSQLPASSWORD']
    DB_HOST = os.environ['MYSQLHOST']
    DB_PORT = os.environ.get('MYSQLPORT', '3306')
    DB_NAME = os.environ['MYSQLDATABASE']
else:
    # Local development fallback (.env file)
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASS = os.environ.get('DB_PASS')
    if not DB_PASS:
        raise RuntimeError(
            'Neither MYSQLHOST (Railway) nor DB_PASS (.env) is set. '
            'Create a .env file (see .env.example) for local dev, or set '
            'the MYSQLHOST/MYSQLUSER/MYSQLPASSWORD/MYSQLDATABASE variables '
            'on Railway, referencing your MySQL service.'
        )
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '3306')
    DB_NAME = os.environ.get('DB_NAME', 'jewellery_orders')

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASS)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Anchor to the app's actual folder (app.root_path), NOT the process's
# current working directory -- otherwise uploads can be saved to one
# location while Flask's static handler serves from another, and
# images silently fail to load.
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
    """Get all images for an order, falling back to legacy single image."""
    imgs = from_json_filter(order.reference_images)
    if not imgs and order.reference_image:
        imgs = [order.reference_image]
    return imgs

with app.app_context():
    db.create_all()
    # Migration: add new columns if missing
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)

@app.template_filter('img_url')
def img_url_filter(key):
    """
    Converts a stored image key (e.g. "orders/abc123.jpg") into a
    temporary signed URL valid for 15 minutes. The bucket is private --
    no direct access is possible without a signed link.
    Falls back gracefully for old local paths from before cloud storage.
    """
    if not key:
        return ''
    # Already a full URL (very old data, pre-signed-URL migration)
    if key.startswith('http://') or key.startswith('https://'):
        return key
    from utils.storage import get_signed_url
    return get_signed_url(key)


# ── Sync endpoint (/api/sync) ──────────────────────────────────────────────────
# Receives an encrypted snapshot from the local PC's sync.py script
# and imports it into the cloud MySQL database.
import base64 as _b64, hashlib as _hs
from flask import request as _req

@app.route('/api/export', methods=['GET'])
def api_export():
    """
    Returns an encrypted snapshot of the entire cloud database.
    Called by the local sync.py pull_from_cloud() function.
    """
    secret = os.environ.get('SYNC_SECRET', '')
    if not secret:
        return _json.dumps({'ok': False, 'error': 'SYNC_SECRET not set'}), 500

    provided = _req.headers.get('X-Sync-Key', '')
    expected = _hs.sha256(secret.encode()).hexdigest()
    if provided != expected:
        return _json.dumps({'ok': False, 'error': 'Unauthorized'}), 401

    try:
        # Export all tables from cloud MySQL
        from sqlalchemy import text, inspect
        snapshot = {'exported_at': str(db.session.execute(text('SELECT NOW()')).scalar())}
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        with db.engine.connect() as conn:
            for tbl in tables:
                if tbl == 'last_sync':
                    continue
                rows = conn.execute(text(f'SELECT * FROM `{tbl}`')).mappings().all()
                snapshot[tbl] = [dict(r) for r in rows]

        # Encrypt with same key as push
        import base64 as _b64e
        from cryptography.fernet import Fernet
        fkey = _b64e.urlsafe_b64encode(_hs.sha256(secret.encode()).digest())
        encrypted = Fernet(fkey).encrypt(
            _json.dumps(snapshot, default=str).encode()
        )
        return encrypted, 200, {'Content-Type': 'application/octet-stream'}
    except Exception as e:
        import traceback
        return _json.dumps({'ok': False, 'error': str(e), 'trace': traceback.format_exc()}), 500
def api_sync():
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

    # Import order matters for foreign keys:
    # parent tables first, child tables last
    FK_ORDER = [
        'branches', 'users', 'vendors', 'products',
        'customers', 'orders', 'order_status_logs',
    ]

    # Get all table names from the snapshot (excluding metadata key)
    all_tables = [k for k in data if k != 'exported_at']

    # Sort: known FK order first, then any extra tables alphabetically
    def sort_key(t):
        try:    return FK_ORDER.index(t)
        except: return len(FK_ORDER)
    all_tables.sort(key=sort_key)

    with db.engine.begin() as conn:
        conn.execute(text('SET FOREIGN_KEY_CHECKS=0'))

        # Clear all tables in reverse order
        for tbl in reversed(all_tables):
            try:
                conn.execute(text(f'DELETE FROM `{tbl}`'))
            except Exception:
                pass

        conn.execute(text('SET FOREIGN_KEY_CHECKS=1'))

        # Re-insert all rows
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

        # Record sync time
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
