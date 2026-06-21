from app import app
from extensions import db
from models.models import Branch, User, Product, Vendor, Order, OrderStatusLog, Customer
from datetime import date, timedelta

with app.app_context():
    db.create_all()

    print("Clearing old data...")
    db.session.query(OrderStatusLog).delete()
    db.session.query(Order).delete()
    db.session.query(Customer).delete()
    db.session.query(User).delete()
    db.session.query(Branch).delete()
    db.session.query(Product).delete()
    db.session.query(Vendor).delete()
    db.session.commit()

    db.session.add_all([
        Branch(name='Head Office', code='HO'),
        Branch(name='Branch 1',   code='BR1'),
        Branch(name='Branch 2',   code='BR2'),
        Branch(name='Branch 3',   code='BR3'),
        Branch(name='Branch 4',   code='BR4'),
        Branch(name='Branch 5',   code='BR5'),
    ])
    db.session.commit()
    print("Branches seeded.")

    ho = Branch.query.filter_by(code='HO').first()

    admin = User(username='admin', full_name='Admin', role='admin', branch_id=None)
    admin.set_password('admin123')
    db.session.add(admin)

    ho_user = User(username='headoffice', full_name='Head Office', role='headoffice', branch_id=ho.id)
    ho_user.set_password('ho123')
    db.session.add(ho_user)

    for b in Branch.query.filter(Branch.code != 'HO').all():
        u = User(username=b.code.lower(), full_name=b.name, role='branch', branch_id=b.id)
        u.set_password(b.code.lower() + '123')
        db.session.add(u)

    db.session.commit()
    print("Users seeded.")

    for p in ['Necklace','Ring','Bangle','Chain','Earring','Bracelet','Pendant','Anklet']:
        db.session.add(Product(name=p))
    db.session.commit()
    print("Products seeded.")

    db.session.add(Vendor(name='Murugan Gold Works', phone='9876543210'))
    db.session.add(Vendor(name='Sri Balaji Jewels',  phone='9876511111'))
    db.session.add(Vendor(name='Annamalai Gold',     phone='9444422222'))
    db.session.commit()
    print("Vendors seeded.")

    # Sample orders across different branches and statuses
    today = date.today()
    branches = Branch.query.filter(Branch.code != 'HO').all()
    products = Product.query.all()
    vendors  = Vendor.query.all()
    admin_user = User.query.filter_by(username='admin').first()
    ho_user    = User.query.filter_by(username='headoffice').first()

    sample_orders = [
        # (branch_code, customer, product_name, sub_product, purity, weight, vendor_name, status, days_ago, exp_days, design_notes)
        ('BR1', 'Kavitha Rajan',    'Necklace', 'Stone Necklace',       '22K', 32.5,  'Murugan Gold Works', 'pending',              1,  14, 'Three-layered design with ruby stones'),
        ('BR1', 'Meena Sundar',     'Ring',     'Diamond Ring',          '18K',  5.2,  'Sri Balaji Jewels',  'sent_to_vendor',       5,  20, 'Princess cut, size 7'),
        ('BR2', 'Lakshmi Priya',    'Bangle',   'Kadas Set',             '22K', 48.0,  'Annamalai Gold',     'received_at_ho',       8,  18, 'Set of 4, traditional pattern'),
        ('BR2', 'Anitha Selvam',    'Earring',  'Jhumka Earrings',       '22K', 12.3,  'Murugan Gold Works', 'dispatched_to_branch', 12, 15, 'Peacock design with green stones'),
        ('BR3', 'Rajathi Mani',     'Chain',    'Singapore Chain',       '22K', 18.7,  'Sri Balaji Jewels',  'received_at_branch',   20, 10, None),
        ('BR3', 'Santha Kumari',    'Bracelet', 'Gold Bracelet',         '22K', 22.1,  'Annamalai Gold',     'pending',              2,  12, 'Broad design, matte finish'),
        ('BR4', 'Geetha Narayanan', 'Pendant',  'Lakshmi Pendant',       '22K',  8.9,  'Murugan Gold Works', 'sent_to_vendor',       6,  16, 'Medium size with chain'),
        ('BR4', 'Vimala Devi',      'Necklace', 'Bridal Necklace Set',   '22K', 85.0,  'Sri Balaji Jewels',  'received_at_ho',       10, 25, 'Bridal set with matching earrings and tikka'),
        ('BR5', 'Padma Suresh',     'Anklet',   'Kolusu Pair',           '22K', 28.4,  'Annamalai Gold',     'dispatched_to_branch', 15, 20, None),
        ('BR5', 'Usha Krishnan',    'Ring',     'Engagement Ring',       '18K',  6.8,  'Murugan Gold Works', 'pending',              0,  10, 'Solitaire, size 6, matte band'),
        ('BR1', 'Saranya Mohan',    'Bangle',   'Stone Bangle Pair',     '22K', 36.0,  'Sri Balaji Jewels',  'received_at_branch',   25,  8, None),
        ('BR2', 'Deepa Venkat',     'Chain',    'Box Chain 24 inch',     '22K', 14.5,  'Annamalai Gold',     'sent_to_vendor',       3,  18, 'Lobster clasp'),
    ]

    status_flow = ['pending', 'sent_to_vendor', 'received_at_ho', 'dispatched_to_branch', 'received_at_branch']

    for i, (br_code, cust_name, prod_name, sub_prod, purity, weight, vendor_name, status, days_ago, exp_days, notes) in enumerate(sample_orders):
        branch  = Branch.query.filter_by(code=br_code).first()
        product = next(p for p in products if p.name == prod_name)
        vendor  = next(v for v in vendors  if v.name == vendor_name)
        br_user = User.query.filter_by(username=br_code.lower()).first()

        # Auto-register customer
        customer = Customer.query.filter_by(branch_id=branch.id, name=cust_name).first()
        if not customer:
            customer = Customer(branch_id=branch.id, name=cust_name)
            db.session.add(customer)
            db.session.flush()

        order_date = today - timedelta(days=days_ago)
        month_str  = order_date.strftime('%Y%m')
        prefix     = f"ORD-{br_code}-{month_str}-"
        count      = Order.query.filter(Order.order_number.like(f"{prefix}%")).count()
        order_num  = f"{prefix}{str(count + 1).zfill(4)}"

        order = Order(
            order_number=order_num,
            branch_id=branch.id,
            customer_name=cust_name,
            customer_id=customer.id,
            product_id=product.id,
            sub_product=sub_prod,
            vendor_id=vendor.id,
            weight=weight,
            purity=purity,
            quantity=1,
            design_notes=notes,
            order_date=order_date,
            expected_delivery_date=order_date + timedelta(days=exp_days),
            order_status=status,
            created_by=br_user.id,
        )
        db.session.add(order)
        db.session.flush()

        # Add status log entries to match current status
        status_index = status_flow.index(status)
        for j in range(status_index + 1):
            old = None if j == 0 else status_flow[j - 1]
            new = status_flow[j]
            changer = br_user if new in ('pending', 'sent_to_vendor', 'received_at_branch') else ho_user
            db.session.add(OrderStatusLog(
                order_id=order.id,
                old_status=old,
                new_status=new,
                changed_by=changer.id,
                remarks=None,
            ))

    db.session.commit()
    print(f"Sample orders seeded ({len(sample_orders)} orders).")

    print("\nDone! Login credentials:")
    for u in User.query.all():
        print(f"  {u.username} / {u.username.replace('headoffice','ho')}123  [{u.role}]")
