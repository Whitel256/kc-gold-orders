from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from models.models import Vendor, Product, User, Branch
from extensions import db

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('main.login'))
        if session.get('user_role') != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('orders.dashboard'))
        return f(*args, **kwargs)
    return decorated

@admin_bp.route('/admin')
@admin_required
def admin_panel():
    vendors = Vendor.query.filter_by(is_active=True).order_by(Vendor.name).all()
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    users = User.query.filter_by(is_active=True).all()
    branches = Branch.query.filter_by(is_active=True).all()
    return render_template('admin/panel.html', vendors=vendors, products=products, users=users, branches=branches)

@admin_bp.route('/admin/vendors/add', methods=['POST'])
@admin_required
def add_vendor():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Vendor name is required.', 'error')
        return redirect(url_for('admin.admin_panel') + '#vendors')
    if Vendor.query.filter_by(name=name, is_active=True).first():
        flash('A vendor with that name already exists.', 'error')
        return redirect(url_for('admin.admin_panel') + '#vendors')
    v = Vendor(name=name, phone=request.form.get('phone','').strip() or None,
               address=request.form.get('address','').strip() or None)
    db.session.add(v)
    db.session.commit()
    flash('Vendor added.', 'success')
    return redirect(url_for('admin.admin_panel') + '#vendors')

@admin_bp.route('/admin/vendors/delete/<int:vid>', methods=['POST'])
@admin_required
def delete_vendor(vid):
    v = Vendor.query.get_or_404(vid)
    v.is_active = False
    db.session.commit()
    flash('Vendor removed.', 'success')
    return redirect(url_for('admin.admin_panel') + '#vendors')

@admin_bp.route('/admin/products/add', methods=['POST'])
@admin_required
def add_product():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Product name is required.', 'error')
        return redirect(url_for('admin.admin_panel') + '#products')
    if Product.query.filter_by(name=name, is_active=True).first():
        flash('That product already exists.', 'error')
        return redirect(url_for('admin.admin_panel') + '#products')
    db.session.add(Product(name=name))
    db.session.commit()
    flash('Product added.', 'success')
    return redirect(url_for('admin.admin_panel') + '#products')

@admin_bp.route('/admin/users/add', methods=['POST'])
@admin_required
def add_user():
    username  = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    role      = request.form.get('role', '').strip()
    password  = request.form.get('password', '').strip()
    branch_id = request.form.get('branch_id') or None

    errors = []
    if not username:  errors.append('Username is required.')
    if not full_name: errors.append('Full name is required.')
    if not password or len(password) < 6:
        errors.append('Password must be at least 6 characters.')
    if role not in ('admin', 'headoffice', 'branch'):
        errors.append('Invalid role.')
    if role == 'branch' and not branch_id:
        errors.append('Branch is required for branch users.')
    if User.query.filter_by(username=username).first():
        errors.append(f'Username "{username}" is already taken.')

    if errors:
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('admin.admin_panel') + '#users')

    u = User(
        username=username,
        full_name=full_name,
        role=role,
        branch_id=int(branch_id) if branch_id else None
    )
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    flash(f'User "{username}" added.', 'success')
    return redirect(url_for('admin.admin_panel') + '#users')

@admin_bp.route('/admin/users/reset-password/<int:uid>', methods=['POST'])
@admin_required
def reset_password(uid):
    u = User.query.get_or_404(uid)
    new_pass = request.form.get('new_password', '').strip()
    if not new_pass or len(new_pass) < 6:
        flash('Password must be at least 6 characters.', 'error')
        return redirect(url_for('admin.admin_panel') + '#users')
    u.set_password(new_pass)
    db.session.commit()
    flash(f'Password reset for {u.full_name}.', 'success')
    return redirect(url_for('admin.admin_panel') + '#users')

@admin_bp.route('/admin/users/deactivate/<int:uid>', methods=['POST'])
@admin_required
def deactivate_user(uid):
    if uid == session['user_id']:
        flash("You can't deactivate your own account.", 'error')
        return redirect(url_for('admin.admin_panel') + '#users')
    u = User.query.get_or_404(uid)
    u.is_active = False
    db.session.commit()
    flash(f'User "{u.username}" deactivated.', 'success')
    return redirect(url_for('admin.admin_panel') + '#users')
