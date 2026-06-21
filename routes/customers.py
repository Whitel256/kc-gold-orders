from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from models.models import Customer, Order, Branch
from extensions import db
from routes.orders import login_required

customers_bp = Blueprint('customers', __name__)

@customers_bp.route('/customers')
@login_required
def list_customers():
    role      = session['user_role']
    branch_id = session.get('branch_id')
    search    = request.args.get('search', '').strip()

    q = Customer.query
    if role == 'branch':
        q = q.filter_by(branch_id=branch_id)

    if search:
        like = f"%{search}%"
        q = q.filter(
            db.or_(Customer.name.ilike(like), Customer.phone.ilike(like))
        )

    customers = q.order_by(Customer.name).all()

    # Annotate with order count
    enriched = []
    for c in customers:
        order_count = Order.query.filter_by(customer_id=c.id).count()
        enriched.append({'customer': c, 'order_count': order_count})

    return render_template('customers/list.html', enriched=enriched, search=search)

@customers_bp.route('/customers/<int:customer_id>')
@login_required
def customer_detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    role      = session['user_role']

    # Branch scoping
    if role == 'branch' and customer.branch_id != session.get('branch_id'):
        flash('Access denied.', 'error')
        return redirect(url_for('customers.list_customers'))

    orders = Order.query.filter_by(customer_id=customer.id)\
                        .order_by(Order.created_at.desc()).all()

    from routes.orders import STATUS_LABELS, STATUS_COLORS
    return render_template('customers/detail.html',
        customer=customer, orders=orders,
        STATUS_LABELS=STATUS_LABELS, STATUS_COLORS=STATUS_COLORS)
