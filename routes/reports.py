from flask import Blueprint, render_template, session, redirect, url_for
from models.models import Order, Branch, Vendor, Product, OrderStatusLog
from extensions import db
from routes.orders import login_required, STATUS_LABELS
from datetime import date
from sqlalchemy import func

reports_bp = Blueprint('reports', __name__)

def get_base_query(role, branch_id):
    q = Order.query
    if role == 'branch':
        q = q.filter_by(branch_id=branch_id)
    return q

@reports_bp.route('/reports')
@login_required
def index():
    return redirect('/reports/branch')

@reports_bp.route('/reports/branch')
@login_required
def branch_report():
    role      = session['user_role']
    branch_id = session.get('branch_id')
    today     = date.today()

    if role == 'branch':
        branches = Branch.query.filter_by(id=branch_id).all()
    else:
        branches = Branch.query.filter(Branch.code != 'HO').order_by(Branch.name).all()

    data = []
    for b in branches:
        bq = Order.query.filter_by(branch_id=b.id)
        total    = bq.count()
        delivered = bq.filter_by(order_status='received_at_branch').count()
        overdue  = bq.filter(
            Order.expected_delivery_date < today,
            Order.order_status != 'received_at_branch'
        ).count()
        data.append({
            'branch':    b,
            'total':     total,
            'pending':   bq.filter_by(order_status='pending').count(),
            'sent_to_vendor': bq.filter_by(order_status='sent_to_vendor').count(),
            'received_at_ho': bq.filter_by(order_status='received_at_ho').count(),
            'dispatched_to_branch': bq.filter_by(order_status='dispatched_to_branch').count(),
            'delivered': delivered,
            'overdue':   overdue,
            'completion_pct': round((delivered / total * 100)) if total else 0,
        })

    return render_template('reports/branch.html', data=data, STATUS_LABELS=STATUS_LABELS)

@reports_bp.route('/reports/vendor')
@login_required
def vendor_report():
    role      = session['user_role']
    branch_id = session.get('branch_id')
    today     = date.today()

    vendors = Vendor.query.filter_by(is_active=True).order_by(Vendor.name).all()
    data = []
    for v in vendors:
        vq = Order.query.filter_by(vendor_id=v.id)
        if role == 'branch':
            vq = vq.filter_by(branch_id=branch_id)
        total     = vq.count()
        delivered = vq.filter_by(order_status='received_at_branch').count()
        active    = vq.filter(Order.order_status.in_(['sent_to_vendor','received_at_ho'])).count()
        overdue   = vq.filter(
            Order.expected_delivery_date < today,
            Order.order_status != 'received_at_branch'
        ).count()
        total_weight = db.session.query(func.sum(Order.weight)).filter(
            Order.vendor_id == v.id,
            Order.order_status.in_(['sent_to_vendor', 'received_at_ho'])
        ).scalar() or 0
        if role == 'branch':
            total_weight = db.session.query(func.sum(Order.weight)).filter(
                Order.vendor_id == v.id,
                Order.branch_id == branch_id,
                Order.order_status.in_(['sent_to_vendor', 'received_at_ho'])
            ).scalar() or 0
        if total == 0:
            continue
        data.append({
            'vendor':       v,
            'total':        total,
            'active':       active,
            'delivered':    delivered,
            'overdue':      overdue,
            'pending_weight': round(total_weight, 2),
        })

    return render_template('reports/vendor.html', data=data)

@reports_bp.route('/reports/monthly')
@login_required
def monthly_report():
    role      = session['user_role']
    branch_id = session.get('branch_id')

    q = Order.query
    if role == 'branch':
        q = q.filter_by(branch_id=branch_id)

    rows = db.session.query(
        func.date_format(Order.order_date, '%Y-%m').label('month'),
        func.count(Order.id).label('total'),
        func.sum(db.case((Order.order_status == 'received_at_branch', 1), else_=0)).label('delivered'),
        func.sum(db.case((Order.order_status != 'received_at_branch', 1), else_=0)).label('in_progress'),
        func.sum(Order.weight).label('total_weight'),
    )
    if role == 'branch':
        rows = rows.filter(Order.branch_id == branch_id)
    rows = rows.group_by('month').order_by(db.desc('month')).limit(12).all()

    data = []
    for r in rows:
        data.append({
            'month':        r.month,
            'total':        r.total,
            'delivered':    int(r.delivered or 0),
            'in_progress':  int(r.in_progress or 0),
            'total_weight': round(float(r.total_weight or 0), 2),
            'completion_pct': round((int(r.delivered or 0) / r.total * 100)) if r.total else 0,
        })

    return render_template('reports/monthly.html', data=data)

@reports_bp.route('/reports/overdue')
@login_required
def overdue_report():
    role      = session['user_role']
    branch_id = session.get('branch_id')
    today     = date.today()

    q = Order.query.filter(
        Order.expected_delivery_date < today,
        Order.order_status != 'received_at_branch'
    )
    if role == 'branch':
        q = q.filter_by(branch_id=branch_id)
    orders = q.order_by(Order.expected_delivery_date.asc()).all()

    from datetime import timedelta
    enriched = []
    for o in orders:
        days_overdue = (today - o.expected_delivery_date).days
        enriched.append({'order': o, 'days_overdue': days_overdue})

    return render_template('reports/overdue.html',
        enriched=enriched, STATUS_LABELS=STATUS_LABELS, today=today)
