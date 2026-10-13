from datetime import date
import sqlite3

from pathlib import Path

from flask import Flask, redirect, render_template_string, request, url_for

app = Flask(__name__)
DB_PATH = Path(__file__).resolve().parent / "inventory.db"


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                sale_date TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)

PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Retail Inventory AI</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f0f4f8;
            padding: 30px;
        }
        .card {
            max-width: 850px;
            margin: auto;
            padding: 30px;
            background: white;
            border-radius: 12px;
        }
        h1 { color: #194b8c; }
        input, button {
            padding: 10px;
            margin: 5px 0;
        }
        button {
            background: #194b8c;
            color: white;
            border: none;
            cursor: pointer;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th { background: #eaf1fa; }
        .error { color: #b42318; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Retail Inventory AI</h1>
        <p>
            <a href="/import-sales">Import Sales</a> |
            <a href="/forecast">Demand Forecast</a>
        </p>

        <form method="post" action="/logout">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button type="submit">Logout</button>
        </form>
        <p>Product and Inventory Management</p>

        {% if error %}
            <p class="error">{{ error }}</p>
        {% endif %}

        <h2>Add Product</h2>
        <form method="post" action="{{ url_for('add_product') }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <input
                name="name"
                placeholder="Product name"
                maxlength="100"
                required
            >
            <input
                type="number"
                name="stock"
                placeholder="Current stock"
                min="0"
                max="1000000"
                required
            >
            <button type="submit">Add Product</button>
        </form>

        <h2>Current Inventory</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>Product</th>
                <th>Current Stock</th>
            </tr>
            {% for product in products %}
            <tr>
                <td>{{ product['id'] }}</td>
                <td>{{ product['name'] }}</td>
                <td>{{ product['stock'] }}</td>
            </tr>
            {% else %}
            <tr>
                <td colspan="3">No products added yet.</td>
            </tr>
            {% endfor %}

        </table>

                <h2>Record Sale</h2>
        <form method="post" action="{{ url_for('record_sale') }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <select name="product_id" required>
                <option value="">Select product</option>
                {% for product in products %}
                <option value="{{ product['id'] }}">
                    {{ product['name'] }} — Stock: {{ product['stock'] }}
                </option>
                {% endfor %}
            </select>

            <input
                type="number"
                name="quantity"
                placeholder="Quantity sold"
                min="1"
                max="1000000"
                required
            >
            <button type="submit">Record Sale</button>
        </form>

        <h2>Recent Sales</h2>
        <table>
            <tr>
                <th>Date</th>
                <th>Product</th>
                <th>Quantity Sold</th>
            </tr>
            {% for sale in sales %}
            <tr>
                <td>{{ sale['sale_date'] }}</td>
                <td>{{ sale['name'] }}</td>
                <td>{{ sale['quantity'] }}</td>
            </tr>
            {% else %}
            <tr>
                <td colspan="3">No sales recorded yet.</td>
            </tr>
            {% endfor %}
        </table>
        
    </div>
</body>
</html>
"""

def show_inventory(error=None, status=200):
    with get_connection() as connection:
        products = connection.execute(
            "SELECT id, name, stock FROM products ORDER BY id"
        ).fetchall()

        sales = connection.execute("""
            SELECT sales.sale_date, products.name, sales.quantity
            FROM sales
            JOIN products ON products.id = sales.product_id
            ORDER BY sales.id DESC
            LIMIT 20
        """).fetchall()

    return render_template_string(
        PAGE,
        products=products,
        sales=sales,
        error=error
    ), status


@app.route("/")
def home():
    return show_inventory()


@app.route("/products/add", methods=["POST"])
def add_product():
    name = request.form.get("name", "").strip()

    try:
        stock = int(request.form.get("stock", ""))
    except ValueError:
        return show_inventory("Stock must be a whole number.", 400)

    if not name or len(name) > 100:
        return show_inventory(
            "Enter a product name between 1 and 100 characters.", 400
        )

    if not 0 <= stock <= 1000000:
        return show_inventory(
            "Stock must be between 0 and 1,000,000.", 400
        )

    try:
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO products (name, stock) VALUES (?, ?)",
                (name, stock)
            )
    except sqlite3.IntegrityError:
        return show_inventory("This product already exists.", 400)

    return redirect(url_for("home"))

@app.route("/sales/add", methods=["POST"])
def record_sale():
    try:
        product_id = int(request.form.get("product_id", ""))
        quantity = int(request.form.get("quantity", ""))
    except ValueError:
        return show_inventory(
            "Select a product and enter a whole-number quantity.", 400
        )

    if not 1 <= quantity <= 1000000:
        return show_inventory(
            "Quantity must be between 1 and 1,000,000.", 400
        )

    with get_connection() as connection:
        # Update only when enough stock is available.
        result = connection.execute("""
            UPDATE products
            SET stock = stock - ?
            WHERE id = ? AND stock >= ?
        """, (quantity, product_id, quantity))

        if result.rowcount != 1:
            return show_inventory(
                "Sale rejected: product not found or insufficient stock.",
                400
            )

        # Both changes commit together, or both roll back.
        connection.execute("""
            INSERT INTO sales (product_id, quantity, sale_date)
            VALUES (?, ?, ?)
        """, (product_id, quantity, date.today().isoformat()))

    return redirect(url_for("home"))
initialize_database()

from data_pipeline import register_data_pipeline
register_data_pipeline(app, DB_PATH)

from forecasting import register_forecasting
register_forecasting(app, DB_PATH)

from security import register_security
register_security(app, DB_PATH)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
