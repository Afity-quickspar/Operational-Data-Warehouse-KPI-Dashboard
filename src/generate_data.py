"""
============================================================================
 SYNTHETIC SOURCE-SYSTEM GENERATOR
============================================================================
Emulates the raw exports you would receive from operational source systems
(billing, product analytics, CRM, ad platforms) as staged CSV / JSON files.

Design goals
------------
* Deterministic (seeded) so every run is reproducible and dbt tests are stable.
* Internally consistent: orders reference real customers, subscriptions align
  with plans, events align with lifecycles, marketing spend explains CAC.
* Economically realistic: a ~12% "high-value" cohort is deliberately seeded to
  concentrate ~38% of gross revenue - the flagship insight of the project.
* Volume: ~350k+ rows total, comfortably clearing the 100k+ requirement.

Outputs (data/raw/):
  customers.csv, orders.csv, subscriptions.csv, web_sessions.csv,
  marketing_spend.csv, events.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

sys.path.append(str(Path(__file__).resolve().parent))
from utils.db import load_config
from utils.logger import get_logger

log = get_logger("generate")


def generate() -> dict[str, int]:
    cfg = load_config()
    g = cfg["generation"]
    raw_dir = Path(cfg["ingestion"]["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)

    seed = int(g["seed"])
    rng = np.random.default_rng(seed)
    fake = Faker()
    Faker.seed(seed)

    start_date = datetime.fromisoformat(g["start_date"])
    end_date = datetime.fromisoformat(g["end_date"])
    span_days = (end_date - start_date).days
    n_customers = int(g["customers"])

    plans = g["plans"]
    regions = g["regions"]
    channels = g["marketing_channels"]

    log.info(f"Generating dataset | customers={n_customers:,} | span={span_days} days "
             f"({g['start_date']} -> {g['end_date']})")

    # ---------------------------------------------------------------------
    # 1. CUSTOMERS  (dimension)
    # ---------------------------------------------------------------------
    # High-value cohort flag: ~12% of the base. These customers order more
    # frequently and at a higher AOV -> they will concentrate ~38% of revenue.
    is_high_value = rng.random(n_customers) < 0.12

    plan_probs_base = np.array([0.34, 0.30, 0.22, 0.10, 0.04])   # Free..Enterprise
    plan_probs_hv = np.array([0.02, 0.10, 0.28, 0.35, 0.25])

    signup_offsets = rng.integers(0, span_days, size=n_customers)
    signup_dates = [start_date + timedelta(days=int(o)) for o in signup_offsets]

    region_choice = rng.choice(regions, size=n_customers, p=[0.46, 0.28, 0.16, 0.10])
    channel_choice = rng.choice(
        channels, size=n_customers, p=[0.24, 0.20, 0.18, 0.12, 0.14, 0.06, 0.06]
    )

    customers = []
    for i in range(n_customers):
        hv = bool(is_high_value[i])
        plan = rng.choice(plans, p=(plan_probs_hv if hv else plan_probs_base))
        company_size = int(rng.choice(
            [5, 25, 100, 500, 2500],
            p=([0.05, 0.15, 0.30, 0.30, 0.20] if hv else [0.40, 0.30, 0.18, 0.09, 0.03])
        ))
        # ~1.5% of emails intentionally missing to exercise dbt null-rate tests
        email = fake.company_email() if rng.random() > 0.015 else ""
        customers.append({
            "customer_id": 100000 + i,
            "customer_name": fake.company(),
            "email": email,
            "signup_date": signup_dates[i].date().isoformat(),
            "region": region_choice[i],
            "country": fake.country_code(),
            "acquisition_channel": channel_choice[i],
            "plan": plan,
            "company_size": company_size,
            "industry": fake.random_element([
                "SaaS", "E-commerce", "Fintech", "Healthcare", "Manufacturing",
                "Media", "Education", "Logistics", "Real Estate", "Gaming",
            ]),
            "is_high_value_seed": int(hv),   # ground-truth label (audit only)
        })
    df_customers = pd.DataFrame(customers)

    # ---------------------------------------------------------------------
    # 2. ORDERS  (fact) - the revenue engine
    # ---------------------------------------------------------------------
    base_orders = float(g["avg_orders_per_customer"])
    order_rows = []
    order_id = 900000
    HV_FREQ_MULT = 2.0     # high-value order-frequency multiplier
    HV_AOV_MULT = 2.25     # high-value average-order-value multiplier

    for i in range(n_customers):
        hv = bool(is_high_value[i])
        signup = signup_dates[i]
        active_days = max((end_date - signup).days, 1)
        lam = base_orders * (active_days / span_days) * (HV_FREQ_MULT if hv else 1.0)
        lam = max(lam, 0.2)
        n_orders = int(rng.poisson(lam))
        if n_orders == 0:
            continue

        mu = np.log(120.0) + (np.log(HV_AOV_MULT) if hv else 0.0)
        amounts = rng.lognormal(mean=mu, sigma=0.55, size=n_orders)

        offs = rng.integers(0, active_days, size=n_orders)
        for k in range(n_orders):
            odate = signup + timedelta(days=int(offs[k]))
            amount = round(float(amounts[k]), 2)
            r = rng.random()
            status = "refunded" if r < 0.04 else ("pending" if r < 0.07 else "completed")
            discount = round(float(rng.choice([0, 0, 0, 5, 10, 15, 20]) / 100.0), 2)
            order_rows.append({
                "order_id": order_id,
                "customer_id": 100000 + i,
                "order_ts": datetime(odate.year, odate.month, odate.day,
                                     int(rng.integers(0, 24)), int(rng.integers(0, 60))).isoformat(),
                "gross_amount": amount,
                "discount_pct": discount,
                "net_amount": round(amount * (1 - discount), 2),
                "num_items": int(rng.integers(1, 8)),
                "channel": rng.choice(channels),
                "status": status,
            })
            order_id += 1
    df_orders = pd.DataFrame(order_rows)

    # ---------------------------------------------------------------------
    # 3. SUBSCRIPTIONS  (fact) - MRR, churn, retention
    # ---------------------------------------------------------------------
    mrr_by_plan = {"Free": 0, "Starter": 49, "Pro": 149, "Business": 499, "Enterprise": 1499}
    sub_rows = []
    for i in range(n_customers):
        plan = df_customers.at[i, "plan"]
        signup = signup_dates[i]
        hv = bool(is_high_value[i])
        base_hazard = {"Free": 0.10, "Starter": 0.07, "Pro": 0.045,
                       "Business": 0.028, "Enterprise": 0.016}[plan]
        if hv:
            base_hazard *= 0.6
        months_active = 0
        max_months = max((end_date - signup).days // 30, 1)
        churned = False
        churn_date = None
        for _m in range(max_months):
            if rng.random() < base_hazard:
                churned = True
                churn_date = (signup + timedelta(days=30 * (months_active + 1)))
                if churn_date > end_date:
                    churn_date = None
                    churned = False
                break
            months_active += 1
        status = "churned" if churned and churn_date else \
                 ("active" if rng.random() > 0.03 else "paused")
        sub_rows.append({
            "subscription_id": 700000 + i,
            "customer_id": 100000 + i,
            "plan": plan,
            "mrr": mrr_by_plan[plan],
            "start_date": signup.date().isoformat(),
            "status": status,
            "churn_date": churn_date.date().isoformat() if (status == "churned" and churn_date) else "",
            "months_active": months_active,
            "billing_interval": rng.choice(["monthly", "annual"], p=[0.7, 0.3]),
        })
    df_subs = pd.DataFrame(sub_rows)

    # ---------------------------------------------------------------------
    # 4. WEB SESSIONS  (fact) - conversion funnel
    # ---------------------------------------------------------------------
    n_sessions = int(g["web_sessions"])
    sess_offsets = rng.integers(0, span_days, size=n_sessions)
    sess_channels = rng.choice(channels, size=n_sessions,
                               p=[0.22, 0.20, 0.24, 0.08, 0.12, 0.06, 0.08])
    conv_base = {"Paid Search": 0.045, "Paid Social": 0.030, "Organic": 0.052,
                 "Referral": 0.065, "Email": 0.075, "Affiliate": 0.028, "Direct": 0.060}
    sess_rows = []
    cust_ids = df_customers["customer_id"].to_numpy()
    for s in range(n_sessions):
        ch = sess_channels[s]
        sdate = start_date + timedelta(days=int(sess_offsets[s]))
        converted = rng.random() < conv_base[ch]
        cust = int(rng.choice(cust_ids)) if converted else ""
        sess_rows.append({
            "session_id": f"S{600000 + s}",
            "session_ts": datetime(sdate.year, sdate.month, sdate.day,
                                   int(rng.integers(0, 24)), int(rng.integers(0, 60))).isoformat(),
            "channel": ch,
            "device": rng.choice(["desktop", "mobile", "tablet"], p=[0.52, 0.42, 0.06]),
            "landing_page": rng.choice(["/", "/pricing", "/features", "/blog", "/demo", "/signup"]),
            "pages_viewed": int(rng.integers(1, 14)),
            "duration_sec": int(rng.integers(5, 1800)),
            "converted": int(converted),
            "customer_id": cust,
        })
    df_sessions = pd.DataFrame(sess_rows)

    # ---------------------------------------------------------------------
    # 5. MARKETING SPEND  (fact) - CAC denominator
    # ---------------------------------------------------------------------
    spend_rows = []
    month_starts = pd.date_range(start_date, end_date, freq="MS")
    for m in month_starts:
        for ch in channels:
            if ch in ("Organic", "Direct"):
                continue  # non-paid channels carry no ad spend
            for region in regions:
                base = {"Paid Search": 42000, "Paid Social": 31000, "Referral": 8000,
                        "Email": 6000, "Affiliate": 12000}.get(ch, 10000)
                region_mult = {"North America": 1.0, "EMEA": 0.7, "APAC": 0.5, "LATAM": 0.3}[region]
                spend = base * region_mult * float(rng.uniform(0.8, 1.2))
                impressions = int(spend * rng.uniform(18, 32))
                clicks = int(impressions * rng.uniform(0.008, 0.03))
                spend_rows.append({
                    "spend_date": m.date().isoformat(),
                    "channel": ch,
                    "region": region,
                    "spend": round(spend, 2),
                    "impressions": impressions,
                    "clicks": clicks,
                })
    df_spend = pd.DataFrame(spend_rows)

    # ---------------------------------------------------------------------
    # 6. EVENTS  (semi-structured JSON) - product engagement
    # ---------------------------------------------------------------------
    events_per_cust = int(g["events_per_customer"])
    event_types = ["page_view", "feature_used", "activation", "invite_sent",
                   "support_ticket", "upgrade_clicked", "export_data", "api_call"]
    event_weights = [0.40, 0.22, 0.05, 0.05, 0.06, 0.05, 0.07, 0.10]
    events = []
    ev_id = 1
    # ~35% of customers are "early-drop": they disengage within their first
    # month, so their events cluster in the first ~3-30 days and they generate
    # no later activity. This is what makes 30-day retention a real, non-
    # saturating signal (dormant users simply stop emitting events).
    early_drop = rng.random(n_customers) < 0.35
    sampled = rng.choice(n_customers, size=min(n_customers, 8000), replace=False)
    for i in sampled:
        hv = bool(is_high_value[i])
        signup = signup_dates[i]
        active_days = max((end_date - signup).days, 1)
        if early_drop[i]:
            horizon = min(active_days, int(rng.integers(3, 30)))
            n_ev = int(rng.poisson(6))                       # few, all early
        else:
            horizon = active_days                            # engaged full life
            n_ev = int(rng.poisson(events_per_cust * (1.6 if hv else 1.0)))
        offs = rng.integers(0, max(horizon, 1), size=n_ev) if n_ev else []
        for k in range(n_ev):
            edate = signup + timedelta(days=int(offs[k]))
            etype = rng.choice(event_types, p=event_weights)
            events.append({
                "event_id": ev_id,
                "customer_id": int(100000 + i),
                "event_type": str(etype),
                "event_ts": datetime(edate.year, edate.month, edate.day,
                                     int(rng.integers(0, 24)), int(rng.integers(0, 60)),
                                     int(rng.integers(0, 60))).isoformat(),
                "properties": {
                    "platform": str(rng.choice(["web", "ios", "android", "api"])),
                    "app_version": f"{int(rng.integers(3,6))}.{int(rng.integers(0,12))}.{int(rng.integers(0,20))}",
                    "session_len_sec": int(rng.integers(3, 3600)),
                    "feature": str(rng.choice(["dashboard", "reports", "exports", "billing",
                                               "integrations", "admin", "search"])),
                },
            })
            ev_id += 1

    # ---------------------------------------------------------------------
    # WRITE OUT (mixed CSV + JSON to demonstrate staged multi-format ingest)
    # ---------------------------------------------------------------------
    df_customers.to_csv(raw_dir / "customers.csv", index=False)
    df_orders.to_csv(raw_dir / "orders.csv", index=False)
    df_subs.to_csv(raw_dir / "subscriptions.csv", index=False)
    df_sessions.to_csv(raw_dir / "web_sessions.csv", index=False)
    df_spend.to_csv(raw_dir / "marketing_spend.csv", index=False)
    with open(raw_dir / "events.json", "w", encoding="utf-8") as fh:
        json.dump(events, fh)

    # ---------------------------------------------------------------------
    # AUDIT: report the flagship revenue-concentration insight
    # ---------------------------------------------------------------------
    completed = df_orders[df_orders["status"] == "completed"].copy()
    rev_by_cust = completed.groupby("customer_id")["net_amount"].sum()
    hv_ids = set(df_customers.loc[df_customers["is_high_value_seed"] == 1, "customer_id"])
    hv_rev = rev_by_cust[rev_by_cust.index.isin(hv_ids)].sum()
    total_rev = rev_by_cust.sum()
    hv_share = hv_rev / total_rev if total_rev else 0
    hv_pct_users = len(hv_ids) / n_customers

    counts = {
        "customers": len(df_customers),
        "orders": len(df_orders),
        "subscriptions": len(df_subs),
        "web_sessions": len(df_sessions),
        "marketing_spend": len(df_spend),
        "events": len(events),
    }
    total_rows = sum(counts.values())

    log.info("-" * 64)
    log.info("Row counts by source:")
    for k, v in counts.items():
        log.info(f"    {k:<18} {v:>10,}")
    log.info(f"    {'TOTAL':<18} {total_rows:>10,}")
    log.info("-" * 64)
    log.info(f"Flagship insight -> high-value cohort = {hv_pct_users:.1%} of customers "
             f"drive {hv_share:.1%} of completed-order revenue")
    log.info(f"Gross completed revenue (all-time): ${total_rev:,.0f}")
    log.info("-" * 64)
    log.info(f"Raw files written to: {raw_dir.resolve()}")

    return counts


if __name__ == "__main__":
    generate()
