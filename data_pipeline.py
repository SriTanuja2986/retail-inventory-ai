import sqlite3
from datetime import date

import pandas as pd
from flask import request, render_template_string


def register_data_pipeline(app, db_path):
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

    with sqlite3.connect(db_path) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS historical_sales (
                transaction_id TEXT PRIMARY KEY,
                product_id INTEGER NOT NULL,
                sale_date TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0)
            )
        """)

    @app.route("/import-sales", methods=["GET", "POST"])
    def import_sales():
        message = ""
        rejected = []

        if request.method == "POST":
            uploaded = request.files.get("file")

            if not uploaded or not uploaded.filename.lower().endswith(".csv"):
                message = "Please select a CSV file."
            else:
                try:
                    df = pd.read_csv(
                        uploaded, dtype=str, keep_default_na=False
                    )
                    df.columns = df.columns.str.strip()

                    required = {
                        "transaction_id", "product_id",
                        "sale_date", "quantity"
                    }

                    if not required.issubset(df.columns):
                        raise ValueError(
                            "Required columns: transaction_id, "
                            "product_id, sale_date, quantity"
                        )

                    if len(df) > 10000:
                        raise ValueError("Maximum 10,000 rows per upload.")

                    accepted = 0
                    duplicates = 0

                    with sqlite3.connect(db_path) as connection:
                        product_ids = {
                            row[0] for row in connection.execute(
                                "SELECT id FROM products"
                            )
                        }

                        for number, (_, row) in enumerate(
                            df.iterrows(), start=2
                        ):
                            try:
                                transaction_id = row["transaction_id"].strip()
                                product_id = int(row["product_id"].strip())
                                quantity = int(row["quantity"].strip())
                                sale_date = date.fromisoformat(
                                    row["sale_date"].strip()
                                )

                                if not transaction_id or len(transaction_id) > 100:
                                    raise ValueError("Invalid transaction ID")

                                if product_id not in product_ids:
                                    raise ValueError("Unknown product ID")

                                if not 1 <= quantity <= 1000000:
                                    raise ValueError("Invalid quantity")

                                if sale_date > date.today():
                                    raise ValueError("Future sale date")

                                existing = connection.execute("""
                                    SELECT product_id, sale_date, quantity
                                    FROM historical_sales
                                    WHERE transaction_id = ?
                                """, (transaction_id,)).fetchone()

                                values = (
                                    product_id,
                                    sale_date.isoformat(),
                                    quantity
                                )

                                if existing:
                                    if existing != values:
                                        raise ValueError(
                                            "Transaction ID has conflicting data"
                                        )
                                    duplicates += 1
                                    continue

                                connection.execute("""
                                    INSERT INTO historical_sales
                                    VALUES (?, ?, ?, ?)
                                """, (transaction_id, *values))

                                accepted += 1

                            except ValueError as error:
                                rejected.append(
                                    f"Row {number}: {error}"
                                )

                    message = (
                        f"Accepted: {accepted} | "
                        f"Duplicates skipped: {duplicates} | "
                        f"Rejected: {len(rejected)}"
                    )

                except (ValueError, pd.errors.ParserError,
                        pd.errors.EmptyDataError, UnicodeDecodeError) as error:
                    message = f"Upload failed: {error}"

        with sqlite3.connect(db_path) as connection:
            summary = connection.execute("""
                SELECT h.sale_date, p.name, SUM(h.quantity)
                FROM historical_sales h
                JOIN products p ON p.id = h.product_id
                GROUP BY h.sale_date, p.id, p.name
                ORDER BY h.sale_date DESC, p.name
                LIMIT 50
            """).fetchall()

        return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head><title>Sales Data Import</title></head>
            <body style="font-family:Arial;max-width:900px;margin:40px auto">
                <h1>Sales Data Import</h1>
                <p><a href="/">Back to inventory</a></p>
                <p>Upload historical sales. Current stock is unchanged.</p>
                <form method="post" enctype="multipart/form-data">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <input type="file" name="file" accept=".csv" required>
                    <button type="submit">Upload and Process</button>
                </form>

                <p><strong>{{ message }}</strong></p>
                {% for reason in rejected %}
                    <p>{{ reason }}</p>
                {% endfor %}

                <h2>Daily Historical Sales Summary</h2>
                <table border="1" cellpadding="10">
                    <tr><th>Date</th><th>Product</th><th>Units sold</th></tr>
                    {% for day, name, quantity in summary %}
                    <tr>
                        <td>{{ day }}</td>
                        <td>{{ name }}</td>
                        <td>{{ quantity }}</td>
                    </tr>
                    {% endfor %}
                </table>
            </body>
            </html>
        """, message=message, rejected=rejected, summary=summary)