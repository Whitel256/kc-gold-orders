from flask import Flask, session, redirect, url_for
from urllib.parse import quote_plus
from extensions import db
import os

app = Flask(__name__)

# Load from environment, fall back to dev defaults
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

# Railway provides a ready-made connection string when you add its MySQL
# plugin (MYSQL_URL or MYSQL_PUBLIC_URL, depending on internal/external
# networking). Prefer that if it's present. Otherwise fall back to the
# individual DB_* vars, used for local development.
_railway_url = os.environ.get('MYSQL_URL') or os.environ.get('MYSQL_PUBLIC_URL')

if _railway_url:
    # Railway's URL uses the mysql:// scheme; SQLAlchemy needs mysql+pymysql://
    app.config['SQLALCHEMY_DATABASE_URI'] = _railway_url.replace('mysql://', 'mysql+pymysql://', 1)
else:
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASS = os.environ.get('DB_PASS')
    if not DB_PASS:
        raise RuntimeError(
            'DB_PASS environment variable is not set. Create a .env file '
            '(see .env.example) or set it in your hosting platform.'
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
def img_url_filter(path):
    """
    Renders an image reference correctly whether it's a full R2/S3 URL
    (new uploads) or an old local 'uploads/xxx.jpg' path left over from
    before the cloud-storage migration.
    """
    if not path:
        return ''
    if path.startswith('http://') or path.startswith('https://'):
        return path
    from flask import url_for
    return url_for('static', filename=path)
