import csv
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

folder = Path(__file__).resolve().parent
random_generator = random.Random(42)

with sqlite3.connect(folder / "inventory.db") as connection:
    products = connection.execute(
        "SELECT id, name FROM products ORDER BY id"
    ).fetchall()

# End before the small sample CSV's October dates.
end_date = date(2026, 9, 30)
start_date = end_date - timedelta(days=89)

output = folder / "synthetic_sales_90_days.csv"

with output.open("w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow([
        "transaction_id", "product_id", "sale_date", "quantity"
    ])

    for position, (product_id, name) in enumerate(products):
        base_sales = [12, 4, 6, 15][position % 4]

        for day_number in range(90):
            sale_date = start_date + timedelta(days=day_number)

            weekend_extra = (
                base_sales * 0.3
                if sale_date.weekday() >= 5
                else 0
            )
            gradual_growth = day_number * 0.02
            variation = random_generator.randint(-2, 2)

            quantity = max(
                1,
                round(
                    base_sales
                    + weekend_extra
                    + gradual_growth
                    + variation
                )
            )

            writer.writerow([
                f"SYNTH-{product_id}-{sale_date.isoformat()}",
                product_id,
                sale_date.isoformat(),
                quantity
            ])

print(f"Created: {output}")
print(f"Rows: {len(products) * 90}")
print("Synthetic demonstration data, not real shop sales.")