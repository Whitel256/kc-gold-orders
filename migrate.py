from app import app
from extensions import db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:

        def get_columns(table):
            result = conn.execute(text(f"SHOW COLUMNS FROM `{table}`"))
            return [row[0] for row in result]

        def table_exists(table):
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = :t"
            ), {'t': table})
            return result.scalar() > 0

        print("Checking schema...\n")

        # --- customers table ---
        if not table_exists('customers'):
            conn.execute(text("""
                CREATE TABLE customers (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    branch_id INT NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    phone VARCHAR(20),
                    address TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (branch_id) REFERENCES branches(id)
                )
            """))
            conn.commit()
            print("✓ Created 'customers' table")
        else:
            print("✓ 'customers' table already exists")

        # --- orders table: add customer_id if missing ---
        if table_exists('orders'):
            order_cols = get_columns('orders')
            if 'customer_id' not in order_cols:
                conn.execute(text(
                    "ALTER TABLE orders ADD COLUMN customer_id INT NULL, "
                    "ADD CONSTRAINT fk_orders_customer "
                    "FOREIGN KEY (customer_id) REFERENCES customers(id)"
                ))
                conn.commit()
                print("✓ Added 'customer_id' column to 'orders'")
            else:
                print("✓ 'customer_id' already exists in 'orders'")

        # --- users table: add password_hash if missing ---
        if table_exists('users'):
            user_cols = get_columns('users')
            if 'password_hash' not in user_cols:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''"
                ))
                conn.commit()
                print("✓ Added 'password_hash' column to 'users'")
            else:
                print("✓ 'password_hash' already exists in 'users'")

        print("\nMigration complete!")
