import math
import sqlite3
from datetime import date, timedelta

import pandas as pd
from flask import render_template_string
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error


def register_forecasting(app, db_path):

    @app.route("/forecast")
    def forecast():
        results = []

        with sqlite3.connect(db_path) as connection:
            products = connection.execute(
                "SELECT id, name, stock FROM products ORDER BY id"
            ).fetchall()

            for product_id, name, stock in products:
                df = pd.read_sql_query("""
                    SELECT sale_date, SUM(quantity) AS quantity
                    FROM historical_sales
                    WHERE product_id = ?
                    GROUP BY sale_date
                    ORDER BY sale_date
                """, connection, params=(product_id,))

                if len(df) < 42:
                    results.append({
                        "name": name,
                        "error": "Not enough history: need 42 recorded days."
                    })
                    continue

                df["sale_date"] = pd.to_datetime(df["sale_date"])
                start = df["sale_date"].min()

                df["day_index"] = (
                    df["sale_date"] - start
                ).dt.days
                df["weekday"] = df["sale_date"].dt.dayofweek

                features = ["day_index", "weekday"]
                train = df.iloc[:-14]
                test = df.iloc[-14:]

                model = RandomForestRegressor(
                    n_estimators=100,
                    min_samples_leaf=3,
                    random_state=42,
                    n_jobs=1
                )

                model.fit(train[features], train["quantity"])
                predictions = model.predict(test[features])

                baseline_value = float(
                    train["quantity"].tail(7).mean()
                )

                model_mae = mean_absolute_error(
                    test["quantity"], predictions
                )
                baseline_mae = mean_absolute_error(
                    test["quantity"],
                    [baseline_value] * len(test)
                )

                use_model = model_mae < baseline_mae
                chosen = (
                    "Random Forest" if use_model
                    else "Recent-average baseline"
                )

                # Refit using all available history.
                model.fit(df[features], df["quantity"])

                last_recorded = df["sale_date"].max().date()
                forecast_start = max(
                    date.today(),
                    last_recorded + timedelta(days=1)
                )
                future_dates = [
                    forecast_start + timedelta(days=i)
                    for i in range(7)
                ]

                future_features = pd.DataFrame({
                    "day_index": [
                        (day - start.date()).days
                        for day in future_dates
                    ],
                    "weekday": [
                        day.weekday() for day in future_dates
                    ]
                })

                if use_model:
                    daily_forecast = model.predict(future_features)
                else:
                    daily_forecast = [
                        float(df["quantity"].tail(7).mean())
                    ] * 7

                demand = math.ceil(sum(
                    max(0, float(value))
                    for value in daily_forecast
                ))

                # Demo policy: 20% safety stock, no incoming orders.
                safety_stock = math.ceil(demand * 0.20)
                suggested_order = max(
                    0, demand + safety_stock - stock
                )

                stale_days = (
                    date.today() - last_recorded
                ).days

                results.append({
                    "name": name,
                    "stock": stock,
                    "demand": demand,
                    "safety": safety_stock,
                    "order": suggested_order,
                    "model_mae": round(model_mae, 2),
                    "baseline_mae": round(baseline_mae, 2),
                    "chosen": chosen,
                    "start": future_dates[0].isoformat(),
                    "end": future_dates[-1].isoformat(),
                    "last_recorded": last_recorded.isoformat(),
                    "stale": stale_days > 7,
                    "error": None
                })

        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Demand Forecasting</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background: #f0f4f8;
                    margin: 30px;
                }
                .card {
                    background: white;
                    padding: 24px;
                    margin-bottom: 20px;
                    border-radius: 12px;
                }
                h1, h2 { color: #194b8c; }
                table {
                    width: 100%;
                    border-collapse: collapse;
                }
                td, th {
                    padding: 10px;
                    border: 1px solid #ddd;
                    text-align: left;
                }
                .warning { color: #a14400; }
            </style>
        </head>
        <body>
            <h1>Demand Forecasting and Restocking</h1>
            <p>
                <a href="/">Inventory</a> |
                <a href="/import-sales">Import sales</a>
            </p>
            <p>
                Demo uses synthetic historical data.
                MAE is average daily prediction error in units;
                lower is better.
            </p>
            <p>
                Evaluation: train on earlier records and compare
                predictions on the final 14 recorded days.
                These scores guide model selection.
            </p>

            {% for item in results %}
            <div class="card">
                <h2>{{ item.name }}</h2>

                {% if item.error %}
                    <p>{{ item.error }}</p>
                {% else %}
                    <p>
                        Forecast period: {{ item.start }}
                        to {{ item.end }}
                    </p>
                    <p>
                        Latest historical date:
                        {{ item.last_recorded }}
                    </p>

                    {% if item.stale %}
                    <p class="warning">
                        History is over 7 days old.
                        Treat this forecast as provisional.
                    </p>
                    {% endif %}

                    <table>
                        <tr>
                            <th>Current stock</th>
                            <th>7-day demand</th>
                            <th>Safety stock</th>
                            <th>Suggested order</th>
                        </tr>
                        <tr>
                            <td>{{ item.stock }}</td>
                            <td>{{ item.demand }}</td>
                            <td>{{ item.safety }}</td>
                            <td>{{ item.order }}</td>
                        </tr>
                    </table>

                    <p>Selected method: {{ item.chosen }}</p>
                    <p>
                        Random Forest MAE: {{ item.model_mae }} |
                        Baseline MAE: {{ item.baseline_mae }}
                    </p>
                    <p>
                        Order calculation:
                        max(0, {{ item.demand }} + {{ item.safety }}
                        - {{ item.stock }}) = {{ item.order }}
                    </p>
                {% endif %}
            </div>
            {% endfor %}

            <p>
                Demo assumption: a 7-day stock coverage period,
                20% safety stock, and no incoming orders.
                Forecasting currently uses imported history only.
                Missing dates are not automatically treated as zero sales.
            </p>
        </body>
        </html>
        """, results=results)