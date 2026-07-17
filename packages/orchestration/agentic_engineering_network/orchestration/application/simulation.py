from __future__ import annotations


def run_estimate_simulations(monthly_visitors: int = 1000, conversion_rate: float = 0.03, price: float = 29.0) -> dict[str, object]:
    customers = round(monthly_visitors * conversion_rate)
    monthly_revenue = round(customers * price, 2)
    churned = round(customers * 0.04)
    support_hours = round(customers * 0.25, 1)
    infrastructure_cost = round(80 + customers * 0.85, 2)
    return {
        "estimate_notice": "Simulations are estimates, not guarantees.",
        "inputs": {
            "monthly_visitors": monthly_visitors,
            "conversion_rate": conversion_rate,
            "price": price,
        },
        "user_growth": {"new_customers_per_month": customers, "assumption": "linear visitor volume"},
        "infrastructure_costs": {"monthly_usd": infrastructure_cost, "assumption": "small B2B SaaS baseline"},
        "churn": {"monthly_churned_customers": churned, "assumption": "4 percent monthly churn until validated"},
        "pricing": {"monthly_recurring_revenue": monthly_revenue, "assumption": "single blended price"},
        "conversion_funnels": {
            "visitors": monthly_visitors,
            "signups": round(monthly_visitors * conversion_rate * 2),
            "paid_customers": customers,
        },
        "scaling_bottlenecks": ["database indexes", "background jobs", "webhook retries", "model inference queue"],
        "operational_load": {"support_hours_per_month": support_hours, "assumption": "0.25 support hours/customer/month"},
    }
