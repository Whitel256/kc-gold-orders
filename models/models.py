from extensions import db
from datetime import datetime

class Branch(db.Model):
    __tablename__ = 'branches'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False, default='')
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, headoffice, branch
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    branch = db.relationship('Branch', backref='users')

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

class Vendor(db.Model):
    __tablename__ = 'vendors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(30), unique=True, nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    sub_product = db.Column(db.String(100), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=False)
    weight = db.Column(db.Numeric(8, 3), nullable=False)
    size = db.Column(db.String(50))
    purity = db.Column(db.String(10), default='22K')
    quantity = db.Column(db.Integer, default=1)
    design_notes = db.Column(db.Text)
    order_no         = db.Column(db.String(100), unique=True, nullable=True)  # manual order number
    reference_image  = db.Column(db.String(500))   # legacy single image (kept for migration)
    reference_images = db.Column(db.Text, default='[]')  # JSON list of up to 3 image paths
    order_date = db.Column(db.Date, nullable=False)
    expected_delivery_date = db.Column(db.Date)
    order_status = db.Column(db.String(30), default='pending')
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    branch = db.relationship('Branch', backref='orders')
    product = db.relationship('Product', backref='orders')
    vendor = db.relationship('Vendor', backref='orders')
    created_by_user = db.relationship('User', backref='orders')

class OrderStatusLog(db.Model):
    __tablename__ = 'order_status_logs'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    old_status = db.Column(db.String(30))
    new_status = db.Column(db.String(30), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    remarks = db.Column(db.Text)

    order = db.relationship('Order', backref='status_logs')
    changed_by_user = db.relationship('User', backref='status_logs')


class Customer(db.Model):
    __tablename__ = 'customers'
    id         = db.Column(db.Integer, primary_key=True)
    branch_id  = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    name       = db.Column(db.String(100), nullable=False)
    phone      = db.Column(db.String(20), nullable=True)
    address    = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    branch = db.relationship('Branch', backref='customers')
    orders = db.relationship('Order', backref='customer', lazy=True,
                             foreign_keys='Order.customer_id')
