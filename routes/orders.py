from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from models.models import Order, OrderStatusLog, Branch, Product, Vendor, User
from extensions import db
from datetime import datetime, date
import os, uuid
from werkzeug.utils import secure_filename

orders_bp = Blueprint('orders', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

STATUS_FLOW = {
    'pending':              'given_to_vendor',
    'given_to_vendor':      'received_at_ho',
    'received_at_ho':       'dispatched_to_branch',
    'dispatched_to_branch': 'delivered',
}

STATUS_ORDER = ['pending', 'given_to_vendor', 'received_at_ho', 'dispatched_to_branch', 'delivered']

STATUS_LABELS = {
    'pending':              'Pending',
    'given_to_vendor':      'Given to Vendor',
    'received_at_ho':       'Received at HO',
    'dispatched_to_branch': 'Dispatched to Branch',
    'delivered':            'Delivered',
    'cancelled':            'Cancelled',
}

STATUS_COLORS = {
    'pending':              'amber',
    'given_to_vendor':      'blue',
    'received_at_ho':       'teal',
    'dispatched_to_branch': 'purple',
    'delivered':            'green',
}

# Role-based permissions for status updates
STATUS_ROLE_ALLOWED = {
    'pending':              ['branch', 'admin'],
    'given_to_vendor':      ['headoffice', 'admin'],
    'received_at_ho':       ['headoffice', 'admin'],
    'dispatched_to_branch': ['branch', 'admin'],
}

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_order_number(branch_code):
    now = datetime.now()
    prefix = f"ORD-{branch_code}-{now.strftime('%Y%m')}-"
    count = Order.query.filter(Order.order_number.like(f"{prefix}%")).count()
    return f"{prefix}{str(count + 1).zfill(4)}"

@orders_bp.route('/dashboard')
@login_required
def dashboard():
    role      = session['user_role']
    branch_id = session.get('branch_id')
    today     = date.today()

    status_filter = request.args.get('status', '')
    search        = request.args.get('search', '').strip()

    query = Order.query
    if role == 'branch':
        query = query.filter_by(branch_id=branch_id)
    if status_filter:
        query = query.filter_by(order_status=status_filter)
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(Order.customer_name.ilike(like), Order.order_number.ilike(like))
        )
    orders = query.order_by(Order.created_at.desc()).all()

    base = Order.query
    if role == 'branch':
        base = base.filter_by(branch_id=branch_id)
    stats = {s: base.filter_by(order_status=s).count() for s in STATUS_LABELS}
    stats['total'] = base.count()

    # Branch breakdown for admin/HO
    branch_stats = []
    if role in ('admin', 'headoffice'):
        for branch in Branch.query.filter(Branch.code != 'HO').order_by(Branch.name).all():
            bq = Order.query.filter_by(branch_id=branch.id)
            branch_stats.append({
                'branch': branch,
                'total':                bq.count(),
                'pending':              bq.filter_by(order_status='pending').count(),
                'given_to_vendor':       bq.filter_by(order_status='given_to_vendor').count(),
                'received_at_ho':       bq.filter_by(order_status='received_at_ho').count(),
                'dispatched_to_branch': bq.filter_by(order_status='dispatched_to_branch').count(),
                'delivered':            bq.filter_by(order_status='delivered').count(),
                'overdue':              bq.filter(
                                            Order.expected_delivery_date < today,
                                            Order.order_status != 'delivered'
                                        ).count(),
                'orders': Order.query.filter_by(branch_id=branch.id)
                                     .order_by(Order.created_at.desc()).all(),
            })

    # Branch-wise pending orders (all except delivered/cancelled)
    PENDING_STATUSES = ['pending', 'given_to_vendor', 'given_to_vendor', 'received_at_ho', 'dispatched_to_branch']
    branch_pending = {}
    if role == 'branch':
        pending_orders = Order.query.filter(
            Order.branch_id == branch_id,
            Order.order_status.in_(PENDING_STATUSES)
        ).order_by(Order.expected_delivery_date.asc()).all()
        if pending_orders:
            branch_pending[session.get('branch_name', 'My Branch')] = pending_orders
    else:
        for branch in Branch.query.filter(Branch.code != 'HO').order_by(Branch.name).all():
            pending_orders = Order.query.filter(
                Order.branch_id == branch.id,
                Order.order_status.in_(PENDING_STATUSES)
            ).order_by(Order.expected_delivery_date.asc()).all()
            if pending_orders:
                branch_pending[branch.name] = pending_orders

    return render_template('dashboard.html',
        orders=orders, stats=stats, branch_stats=branch_stats,
        branch_pending=branch_pending,
        status_filter=status_filter, search=search, today=today,
        STATUS_LABELS=STATUS_LABELS, STATUS_COLORS=STATUS_COLORS, STATUS_FLOW=STATUS_FLOW,
    )

@orders_bp.route('/orders/new', methods=['GET', 'POST'])
@login_required
def new_order():
    if session['user_role'] not in ('branch', 'admin'):
        flash('Only branch users can create orders.', 'error')
        return redirect(url_for('orders.dashboard'))

    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    vendors  = Vendor.query.filter_by(is_active=True).order_by(Vendor.name).all()
    from models.models import Customer
    branch_id = session.get('branch_id')
    existing_customers = Customer.query.filter_by(branch_id=branch_id).order_by(Customer.name).all() if branch_id else []

    if request.method == 'POST':
        errors = []
        customer_name  = request.form.get('customer_name', '').strip()
        product_id     = request.form.get('product_id', '').strip()
        sub_product    = request.form.get('sub_product', '').strip()
        vendor_id      = request.form.get('vendor_id', '').strip()
        weight_str     = request.form.get('weight', '').strip()
        order_date_str = request.form.get('order_date', '').strip()

        order_no = request.form.get('order_no', '').strip()
        if not order_no:
            errors.append('Order No is required.')
        else:
            existing_order = Order.query.filter_by(order_no=order_no).first()
            if existing_order:
                errors.append(f'Order No "{order_no}" already exists. Please use a unique number.')

        if not customer_name: errors.append('Customer name is required.')
        if not product_id:    errors.append('Product is required.')
        if not sub_product:   errors.append('Sub product is required.')
        if not vendor_id:     errors.append('Vendor is required.')
        if not weight_str:
            errors.append('Weight is required.')
        else:
            try:
                weight = float(weight_str)
                if weight <= 0: errors.append('Weight must be greater than 0.')
            except ValueError:
                errors.append('Weight must be a number.')
        if not order_date_str: errors.append('Order date is required.')

        exp_date_str = request.form.get('expected_delivery_date', '').strip()
        if not exp_date_str:
            errors.append('Expected delivery date is required.')

        uploaded_files = request.files.getlist('reference_images')
        uploaded_files = [f for f in uploaded_files if f and f.filename]
        if not uploaded_files:
            errors.append('At least one reference image is required.')

        quantity_str = request.form.get('quantity', '1').strip()
        try:
            quantity = int(quantity_str)
            if quantity < 1: errors.append('Quantity must be at least 1.')
        except ValueError:
            errors.append('Quantity must be a whole number.')

        if errors:
            for e in errors: flash(e, 'error')
            return render_template('orders/form.html', products=products, vendors=vendors, existing_customers=existing_customers,
                                   today=date.today().isoformat(), form=request.form)

        import json as _json
        from utils.storage import upload_image
        image_paths = []
        for f in uploaded_files[:3]:
            url = upload_image(f, folder='orders')
            if url:
                image_paths.append(url)
        if not image_paths:
            flash('Invalid image type. Allowed: png, jpg, jpeg, gif, webp', 'error')
            return render_template('orders/form.html', products=products, vendors=vendors, existing_customers=existing_customers,
                                   today=date.today().isoformat(), form=request.form)
        image_path = image_paths[0]

        branch = Branch.query.get(session['branch_id']) if session['branch_id'] else Branch.query.filter_by(code='HO').first()
        try:
            exp_date = date.fromisoformat(exp_date_str)
        except ValueError:
            exp_date = None

        # Auto-register customer if not exists for this branch
        from models.models import Customer
        customer_phone = request.form.get('customer_phone', '').strip() or None
        customer_address = request.form.get('customer_address', '').strip() or None
        customer = Customer.query.filter_by(branch_id=branch.id, name=customer_name).first()
        if not customer:
            customer = Customer(branch_id=branch.id, name=customer_name,
                                phone=customer_phone, address=customer_address)
            db.session.add(customer)
            db.session.flush()
        else:
            if customer_phone: customer.phone = customer_phone
            if customer_address: customer.address = customer_address

        order = Order(
            order_number=generate_order_number(branch.code),
            order_no=order_no,
            branch_id=branch.id,
            customer_name=customer_name,
            customer_id=customer.id,
            product_id=int(product_id),
            sub_product=sub_product,
            vendor_id=int(vendor_id),
            weight=float(weight_str),
            size=request.form.get('size', '').strip() or None,
            purity=request.form.get('purity', '22K'),
            quantity=quantity,
            design_notes=request.form.get('design_notes', '').strip() or None,
            reference_image=image_path,
            reference_images=_json.dumps(image_paths),
            order_date=date.fromisoformat(order_date_str),
            expected_delivery_date=exp_date,
            order_status='pending',
            created_by=session['user_id']
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderStatusLog(
            order_id=order.id, old_status=None, new_status='pending',
            changed_by=session['user_id']
        ))
        db.session.commit()
        flash('Order created successfully!', 'success')
        return redirect(url_for('orders.order_detail', order_id=order.id))

    return render_template('orders/form.html', products=products, vendors=vendors, existing_customers=existing_customers,
                           today=date.today().isoformat(), form={})

@orders_bp.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    logs  = OrderStatusLog.query.filter_by(order_id=order_id).order_by(OrderStatusLog.changed_at.asc()).all()

    role        = session['user_role']
    next_status = STATUS_FLOW.get(order.order_status)
    can_update  = False
    if next_status:
        if role == 'admin':
            can_update = True
        elif role == 'branch' and order.branch_id == session.get('branch_id') \
                and next_status in ('given_to_vendor', 'delivered'):
            can_update = True
        elif role == 'headoffice' and next_status in ('received_at_ho', 'dispatched_to_branch'):
            can_update = True

    # Previous statuses for reverse
    current_index = STATUS_ORDER.index(order.order_status)
    previous_statuses = STATUS_ORDER[:current_index]  # all statuses before current
    can_reverse = role in ('admin', 'headoffice') and len(previous_statuses) > 0

    return render_template('orders/detail.html',
        order=order, logs=logs, can_update=can_update,
        next_status=next_status,
        can_reverse=can_reverse,
        previous_statuses=previous_statuses,
        STATUS_LABELS=STATUS_LABELS,
        STATUS_COLORS=STATUS_COLORS,
        today=date.today(),
    )

@orders_bp.route('/orders/<int:order_id>/update-status', methods=['POST'])
@login_required
def update_status(order_id):
    order = Order.query.get_or_404(order_id)
    next_status = STATUS_FLOW.get(order.order_status)
    if not next_status:
        flash('Order is already completed.', 'error')
        return redirect(url_for('orders.order_detail', order_id=order_id))

    old_status = order.order_status
    order.order_status = next_status
    remarks = request.form.get('remarks', '').strip() or None
    db.session.add(OrderStatusLog(
        order_id=order.id, old_status=old_status, new_status=next_status,
        changed_by=session['user_id'], remarks=remarks
    ))
    db.session.commit()
    flash(f'Status updated to {STATUS_LABELS[next_status]}', 'success')
    return redirect(url_for('orders.order_detail', order_id=order_id))

@orders_bp.route('/orders/<int:order_id>/reverse-status', methods=['POST'])
@login_required
def reverse_status(order_id):
    role = session['user_role']
    if role not in ('admin', 'headoffice'):
        flash('Not authorized to reverse status.', 'error')
        return redirect(url_for('orders.order_detail', order_id=order_id))

    order       = Order.query.get_or_404(order_id)
    target      = request.form.get('target_status', '').strip()
    reason      = request.form.get('reason', '').strip()

    if not reason:
        flash('A reason is required to reverse the status.', 'error')
        return redirect(url_for('orders.order_detail', order_id=order_id))

    if target not in STATUS_ORDER:
        flash('Invalid target status.', 'error')
        return redirect(url_for('orders.order_detail', order_id=order_id))

    current_index = STATUS_ORDER.index(order.order_status)
    target_index  = STATUS_ORDER.index(target)
    if target_index >= current_index:
        flash('Can only reverse to a previous status.', 'error')
        return redirect(url_for('orders.order_detail', order_id=order_id))

    old_status     = order.order_status
    order.order_status = target
    db.session.add(OrderStatusLog(
        order_id=order.id,
        old_status=old_status,
        new_status=target,
        changed_by=session['user_id'],
        remarks=f'[REVERSED] {reason}'
    ))
    db.session.commit()
    flash(f'Status reversed to "{STATUS_LABELS[target]}"', 'success')
    return redirect(url_for('orders.order_detail', order_id=order_id))

@orders_bp.route('/orders')
@login_required
def orders_list():
    return redirect(url_for('orders.dashboard'))


@orders_bp.route('/manage-orders')
@login_required
def manage_orders():
    role      = session['user_role']
    branch_id = session.get('branch_id')
    today     = date.today()

    branch_filter = request.args.get('branch_id', '').strip()
    vendor_filter = request.args.get('vendor_id', '').strip()
    status_filter = request.args.get('status', '').strip()
    search        = request.args.get('search', '').strip()

    query = Order.query

    # Branch-scoped users can only see their own branch
    if role == 'branch':
        query = query.filter_by(branch_id=branch_id)
    elif branch_filter:
        query = query.filter_by(branch_id=int(branch_filter))

    if vendor_filter:
        query = query.filter_by(vendor_id=int(vendor_filter))
    if status_filter:
        query = query.filter_by(order_status=status_filter)
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(Order.customer_name.ilike(like), Order.order_number.ilike(like))
        )

    orders  = query.order_by(Order.created_at.desc()).all()
    branches = Branch.query.filter(Branch.code != 'HO', Branch.is_active == True).order_by(Branch.name).all()
    vendors  = Vendor.query.filter_by(is_active=True).order_by(Vendor.name).all()

    return render_template('orders/manage.html',
        orders=orders,
        branches=branches,
        vendors=vendors,
        branch_filter=branch_filter,
        vendor_filter=vendor_filter,
        status_filter=status_filter,
        search=search,
        today=today,
        STATUS_LABELS=STATUS_LABELS,
        STATUS_FLOW=STATUS_FLOW,
    )


@orders_bp.route('/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_order(order_id):
    order = Order.query.get_or_404(order_id)
    role  = session['user_role']

    if order.order_status != 'pending':
        flash('Only pending orders can be edited.', 'error')
        return redirect(url_for('orders.order_detail', order_id=order_id))
    if role == 'branch' and order.branch_id != session.get('branch_id'):
        flash('Access denied.', 'error')
        return redirect(url_for('orders.dashboard'))

    from models.models import Vendor
    vendors = Vendor.query.filter_by(is_active=True).order_by(Vendor.name).all()

    if request.method == 'POST':
        errors = []
        customer_name = request.form.get('customer_name', '').strip()
        vendor_id     = request.form.get('vendor_id', '').strip()
        weight_str    = request.form.get('weight', '').strip()
        order_date_str = request.form.get('order_date', '').strip()
        exp_date_str  = request.form.get('expected_delivery_date', '').strip()

        order_no = request.form.get('order_no', '').strip()
        if not order_no:
            errors.append('Order No is required.')
        else:
            existing_order = Order.query.filter_by(order_no=order_no).first()
            if existing_order:
                errors.append(f'Order No "{order_no}" already exists. Please use a unique number.')

        if not customer_name: errors.append('Customer name is required.')
        if not vendor_id:     errors.append('Vendor is required.')
        if not exp_date_str:  errors.append('Expected delivery date is required.')
        if not weight_str:
            errors.append('Weight is required.')
        else:
            try:
                weight = float(weight_str)
                if weight <= 0: errors.append('Weight must be greater than 0.')
            except ValueError:
                errors.append('Weight must be a number.')

        if errors:
            for e in errors: flash(e, 'error')
            return render_template('orders/edit.html', order=order, vendors=vendors)

        order.customer_name = customer_name
        order.vendor_id     = int(vendor_id)
        order.weight        = float(weight_str)
        order.size          = request.form.get('size', '').strip() or None
        order.quantity      = int(request.form.get('quantity', 1))
        order.design_notes  = request.form.get('design_notes', '').strip() or None
        order.order_date    = date.fromisoformat(order_date_str)
        order.expected_delivery_date = date.fromisoformat(exp_date_str)

        # Add new images (up to 3 total)
        import json as _json2
        from utils.storage import upload_image, delete_image
        new_files = request.files.getlist('reference_images')
        new_files = [f for f in new_files if f and f.filename]
        if new_files:
            existing = _json2.loads(order.reference_images or '[]')
            for f in new_files:
                if len(existing) >= 3: break
                url = upload_image(f, folder='orders')
                if url:
                    existing.append(url)
            order.reference_images = _json2.dumps(existing)
            order.reference_image = existing[0] if existing else order.reference_image
        # Handle image removals
        remove_indices = request.form.getlist('remove_image')
        if remove_indices:
            existing = _json2.loads(order.reference_images or '[]')
            for idx in sorted([int(i) for i in remove_indices], reverse=True):
                if 0 <= idx < len(existing):
                    removed_url = existing.pop(idx)
                    delete_image(removed_url)
            order.reference_images = _json2.dumps(existing)
            order.reference_image = existing[0] if existing else None

        db.session.commit()
        flash('Order updated successfully.', 'success')
        return redirect(url_for('orders.order_detail', order_id=order_id))

    return render_template('orders/edit.html', order=order, vendors=vendors)


@orders_bp.route('/orders/<int:order_id>/print')
@login_required
def print_order(order_id):
    order = Order.query.get_or_404(order_id)
    logs  = OrderStatusLog.query.filter_by(order_id=order_id)\
                                .order_by(OrderStatusLog.changed_at.asc()).all()
    from datetime import datetime as dt
    return render_template('orders/print.html',
        order=order, logs=logs,
        STATUS_LABELS=STATUS_LABELS,
        now=dt.now().strftime('%d %b %Y, %I:%M %p'))


@orders_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    order  = Order.query.get_or_404(order_id)
    role   = session['user_role']
    reason = request.form.get('reason', '').strip()

    if order.order_status == 'delivered':
        flash('Cannot cancel a delivered order.', 'error')
        return redirect(url_for('orders.order_detail', order_id=order_id))
    if role not in ('admin', 'headoffice'):
        flash('Only Admin or Head Office can cancel orders.', 'error')
        return redirect(url_for('orders.order_detail', order_id=order_id))
    if not reason:
        flash('A reason is required to cancel an order.', 'error')
        return redirect(url_for('orders.order_detail', order_id=order_id))

    old_status = order.order_status
    order.order_status = 'cancelled'
    db.session.add(OrderStatusLog(
        order_id=order.id, old_status=old_status, new_status='cancelled',
        changed_by=session['user_id'], remarks=f'[CANCELLED] {reason}'
    ))
    db.session.commit()
    flash('Order cancelled.', 'success')
    return redirect(url_for('orders.order_detail', order_id=order_id))
