from flask import Blueprint, render_template, session, redirect, url_for
from routes.orders import login_required

vendors_bp = Blueprint('vendors', __name__)

@vendors_bp.route('/vendors')
@login_required
def list_vendors():
    return render_template('vendors/list.html')

@vendors_bp.route('/vendors/<int:vendor_id>')
@login_required
def vendor_detail(vendor_id):
    return render_template('vendors/detail.html')
