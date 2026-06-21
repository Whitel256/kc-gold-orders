from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from models.models import User, Branch
from extensions import db

main_bp = Blueprint('main', __name__)

STATUS_LABELS = {
    'pending': 'Pending',
    'sent_to_vendor': 'Sent to Vendor',
    'received_at_ho': 'Received at HO',
    'dispatched_to_branch': 'Dispatched to Branch',
    'received_at_branch': 'Received at Branch',
}

@main_bp.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
    return redirect(url_for('orders.dashboard'))

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('orders.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('login.html')

        user = User.query.filter_by(username=username, is_active=True).first()

        if not user or not user.check_password(password):
            flash('Invalid username or password.', 'error')
            return render_template('login.html')

        session['user_id']    = user.id
        session['user_name']  = user.full_name
        session['user_role']  = user.role
        session['branch_id']  = user.branch_id
        session['branch_name'] = user.branch.name if user.branch else 'Head Office'
        return redirect(url_for('orders.dashboard'))

    return render_template('login.html')

@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.login'))
