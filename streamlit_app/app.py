"""
============================================================================
 SELF-SERVE KPI DASHBOARD  (Streamlit)
============================================================================
An interactive, filterable analytics app served straight off the DuckDB
warehouse marts. Six executive KPIs, revenue & growth, the flagship customer-
segmentation story, retention cohorts, acquisition economics, and a no-code
self-serve explorer with a read-only SQL runner.

Run:  streamlit run streamlit_app/app.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data_access as da

# ---------------------------------------------------------------------------
# Page config + theme
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Operational DWH · KPI Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRIMARY = "#2563eb"
GREEN = "#16a34a"
AMBER = "#d97706"
RED = "#dc2626"
SLATE = "#334155"
PALETTE = ["#2563eb", "#7c3aed", "#0891b2", "#16a34a", "#d97706", "#dc2626", "#db2777"]

st.markdown(
    """
    <style>
      .main {background-color: #0e1117;}
      .kpi-card {
        background: linear-gradient(145deg, #1c2333 0%, #161b28 100%);
        border: 1px solid #263143; border-radius: 14px; padding: 18px 20px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25);
      }
      .kpi-label {font-size: 0.80rem; letter-spacing: .04em; color:#94a3b8;
                  text-transform: uppercase; margin-bottom: 4px;}
      .kpi-value {font-size: 1.85rem; font-weight: 700; color:#f1f5f9; line-height:1.1;}
      .kpi-sub {font-size: 0.82rem; margin-top:6px;}
      .pill {display:inline-block; padding:2px 10px; border-radius:999px;
             font-size:0.72rem; font-weight:600;}
      .big-insight {background:linear-gradient(145deg,#132a1e,#0f2018);
             border:1px solid #1f6f43; border-radius:14px; padding:18px 22px;}
      .section-note {color:#94a3b8; font-size:0.9rem;}
      h1,h2,h3 {color:#e2e8f0;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Guard: warehouse must exist
# ---------------------------------------------------------------------------
if not da.warehouse_exists():
    st.error("⚠️ Warehouse not found. Run the pipeline first:\n\n"
             "`python src/orchestrate.py`")
    st.stop()

cfg = da.load_config()
targets = cfg["kpi_targets"]
opts = da.filter_options()

# ---------------------------------------------------------------------------
# Sidebar — branding, freshness, global filters, navigation
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 📊 Operational DWH")
    st.caption("DuckDB · dbt · Streamlit · Power BI")

    manifest_rows = da.q(
        "SELECT count(*) AS n FROM main_marts.fct_orders").iloc[0]["n"]
    max_d = opts["max_date"]
    st.markdown(
        f"<span class='pill' style='background:#14532d;color:#86efac;'>● Warehouse fresh</span>"
        f"<br><span class='section-note'>Latest order date: <b>{max_d}</b> · "
        f"{int(manifest_rows):,} orders modelled</span>",
        unsafe_allow_html=True,
    )
    st.divider()

    page = st.radio(
        "Navigate",
        ["Executive Overview", "Revenue & Growth", "Customer Segments",
         "Retention & Cohorts", "Acquisition & Conversion", "Self-Serve Explorer"],
        label_visibility="collapsed",
    )
    st.divider()

    st.markdown("**Global filters**")
    sel_regions = st.multiselect("Region", opts["regions"], default=opts["regions"])
    sel_plans = st.multiselect("Plan", opts["plans"], default=opts["plans"])
    sel_channels = st.multiselect("Acquisition channel", opts["channels"],
                                  default=opts["channels"])
    date_range = st.date_input(
        "Order date range",
        value=(opts["min_date"], opts["max_date"]),
        min_value=opts["min_date"], max_value=opts["max_date"],
    )
    st.caption("Filters apply to Revenue, Segments and Acquisition views. "
               "Executive KPIs reflect company-wide monthly marts.")

# Normalise date range
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    d0, d1 = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
else:
    d0, d1 = pd.Timestamp(opts["min_date"]), pd.Timestamp(opts["max_date"])


# ---------------------------------------------------------------------------
# Shared filtered datasets
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _orders_all() -> pd.DataFrame:
    df = da.fct_orders()
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["order_month"] = pd.to_datetime(df["order_month"])
    return df


def filtered_orders() -> pd.DataFrame:
    df = _orders_all()
    m = (
        df["region"].isin(sel_regions)
        & df["plan"].isin(sel_plans)
        & df["acquisition_channel"].isin(sel_channels)
        & df["order_date"].between(d0, d1)
    )
    return df.loc[m]


def filtered_segments() -> pd.DataFrame:
    df = da.customer_segments()
    m = (
        df["region"].isin(sel_regions)
        & df["plan"].isin(sel_plans)
        & df["acquisition_channel"].isin(sel_channels)
    )
    return df.loc[m]


def fmt_money(x: float) -> str:
    if abs(x) >= 1_000_000:
        return f"${x/1_000_000:.2f}M"
    if abs(x) >= 1_000:
        return f"${x/1_000:.1f}K"
    return f"${x:,.0f}"


def rag_pill(ok: bool, warn: bool = False) -> str:
    if ok:
        return f"<span class='pill' style='background:#14532d;color:#86efac;'>ON TARGET</span>"
    if warn:
        return f"<span class='pill' style='background:#422006;color:#fcd34d;'>WATCH</span>"
    return f"<span class='pill' style='background:#450a0a;color:#fca5a5;'>OFF TARGET</span>"


def kpi_card(label: str, value: str, sub_html: str = "") -> str:
    return (f"<div class='kpi-card'><div class='kpi-label'>{label}</div>"
            f"<div class='kpi-value'>{value}</div>"
            f"<div class='kpi-sub'>{sub_html}</div></div>")


# ===========================================================================
# PAGE 1 — EXECUTIVE OVERVIEW
# ===========================================================================
if page == "Executive Overview":
    st.title("Executive KPI Overview")
    st.markdown("<span class='section-note'>Company-wide monthly scorecard across the "
                "six headline KPIs. Latest complete month vs. prior month, "
                "measured against board targets.</span>", unsafe_allow_html=True)

    km = da.kpi_monthly().copy()
    km["month"] = pd.to_datetime(km["month"])
    # The trailing month is partial (data cuts off mid-month), so the executive
    # scorecard compares the last two COMPLETE months to keep MoM deltas honest.
    max_order = pd.to_datetime(
        da.q("SELECT max(order_date) AS d FROM main_marts.fct_orders").iloc[0]["d"])
    partial_month = max_order.to_period("M").to_timestamp()
    complete = km[km["month"] < partial_month]
    cur = complete.iloc[-1]
    prev = complete.iloc[-2]
    st.caption(f"Reporting month: **{cur['month_label']}** (last complete month) · "
               f"partial month {partial_month:%Y-%m} excluded from deltas.")
    # Retention uses the latest matured 30-day cohort.
    mature = km[km["cohort_is_mature"] == True]  # noqa: E712
    ret_row = mature.iloc[-1] if len(mature) else cur

    def delta_html(curv, prevv, higher_better=True, pct=False, money=False):
        if prevv in (0, None) or pd.isna(prevv):
            return ""
        change = (curv - prevv) / abs(prevv)
        up = curv >= prevv
        good = up if higher_better else not up
        color = GREEN if good else RED
        arrow = "▲" if up else "▼"
        return (f"<span style='color:{color};'>{arrow} {abs(change)*100:.1f}% MoM</span>")

    c1, c2, c3 = st.columns(3)
    rev_ok = cur["recognized_revenue"] >= targets["gross_revenue_monthly"]
    c1.markdown(kpi_card(
        "Recognized Revenue",
        fmt_money(cur["recognized_revenue"]),
        f"{delta_html(cur['recognized_revenue'], prev['recognized_revenue'])} &nbsp; "
        f"{rag_pill(rev_ok, warn=not rev_ok and cur['recognized_revenue']>=0.9*targets['gross_revenue_monthly'])}"
        f"<br><span class='section-note'>Target {fmt_money(targets['gross_revenue_monthly'])}/mo</span>"),
        unsafe_allow_html=True)

    churn_ok = cur["churn_rate"] <= targets["churn_rate_monthly_max"]
    c2.markdown(kpi_card(
        "Logo Churn (monthly)",
        f"{cur['churn_rate']*100:.2f}%",
        f"{delta_html(cur['churn_rate'], prev['churn_rate'], higher_better=False)} &nbsp; "
        f"{rag_pill(churn_ok)}"
        f"<br><span class='section-note'>Ceiling {targets['churn_rate_monthly_max']*100:.1f}%</span>"),
        unsafe_allow_html=True)

    cac_ok = cur["cac"] <= targets["cac_max"]
    c3.markdown(kpi_card(
        "CAC (blended)",
        fmt_money(cur["cac"]),
        f"{delta_html(cur['cac'], prev['cac'], higher_better=False)} &nbsp; "
        f"{rag_pill(cac_ok)}"
        f"<br><span class='section-note'>Ceiling {fmt_money(targets['cac_max'])}</span>"),
        unsafe_allow_html=True)

    c4, c5, c6 = st.columns(3)
    ltv_ok = cur["ltv"] >= targets["ltv_min"]
    ratio = cur["ltv"] / cur["cac"] if cur["cac"] else 0
    c4.markdown(kpi_card(
        "Customer LTV",
        fmt_money(cur["ltv"]),
        f"LTV:CAC <b>{ratio:.1f}×</b> &nbsp; {rag_pill(ratio >= targets['ltv_cac_ratio_min'], warn=ratio>=2)}"
        f"<br><span class='section-note'>Floor {fmt_money(targets['ltv_min'])} · target ratio ≥ {targets['ltv_cac_ratio_min']}×</span>"),
        unsafe_allow_html=True)

    conv_ok = cur["conversion_rate"] >= targets["conversion_rate_min"]
    c5.markdown(kpi_card(
        "Web→Signup Conversion",
        f"{cur['conversion_rate']*100:.2f}%",
        f"{delta_html(cur['conversion_rate'], prev['conversion_rate'])} &nbsp; {rag_pill(conv_ok)}"
        f"<br><span class='section-note'>Floor {targets['conversion_rate_min']*100:.1f}%</span>"),
        unsafe_allow_html=True)

    ret_ok = ret_row["retention_30d"] >= targets["retention_30d_min"]
    c6.markdown(kpi_card(
        "30-Day Retention",
        f"{ret_row['retention_30d']*100:.1f}%",
        f"cohort {ret_row['month_label']} &nbsp; {rag_pill(ret_ok, warn=ret_row['retention_30d']>=0.5)}"
        f"<br><span class='section-note'>Floor {targets['retention_30d_min']*100:.0f}% (last matured cohort)</span>"),
        unsafe_allow_html=True)

    st.markdown("")
    # Flagship insight banner
    seg = da.customer_segments()
    p_users = seg["priority_customer_share"].max() * 100
    p_rev = seg["priority_revenue_share"].max() * 100
    st.markdown(
        f"<div class='big-insight'>💡 <b>Flagship insight —</b> the high-value priority "
        f"segment is just <b>{p_users:.0f}%</b> of customers but drives "
        f"<b>{p_rev:.0f}%</b> of all recognized revenue. Concentrating retention and "
        f"expansion motions on this cohort is the single highest-leverage play.</div>",
        unsafe_allow_html=True)

    st.markdown("### Revenue & customer trend")
    left, right = st.columns([3, 2])
    with left:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=km["month"], y=km["recognized_revenue"],
                             name="Recognized revenue", marker_color=PRIMARY))
        fig.add_trace(go.Scatter(x=km["month"], y=km["active_mrr"], name="Active MRR",
                                 yaxis="y2", line=dict(color=AMBER, width=3)))
        fig.add_hline(y=targets["gross_revenue_monthly"], line_dash="dot",
                      line_color=GREEN, annotation_text="Revenue target")
        fig.update_layout(
            template="plotly_dark", height=380, margin=dict(l=10, r=10, t=30, b=10),
            yaxis=dict(title="Revenue ($)"), yaxis2=dict(title="MRR ($)", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.12), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        fig2 = px.area(km, x="month", y="active_customers",
                       title="Active customers", color_discrete_sequence=[PRIMARY])
        fig2.update_layout(template="plotly_dark", height=380,
                           margin=dict(l=10, r=10, t=40, b=10),
                           paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("### KPI scorecard (last 12 months)")
    scorecard = km.tail(12)[[
        "month_label", "recognized_revenue", "active_customers", "churn_rate",
        "cac", "ltv", "conversion_rate", "retention_30d"]].copy()
    scorecard.columns = ["Month", "Revenue", "Active", "Churn", "CAC", "LTV",
                         "Conversion", "Retention 30d"]
    st.dataframe(
        scorecard.style.format({
            "Revenue": "${:,.0f}", "CAC": "${:,.0f}", "LTV": "${:,.0f}",
            "Churn": "{:.1%}", "Conversion": "{:.1%}", "Retention 30d": "{:.1%}",
            "Active": "{:,.0f}"}),
        use_container_width=True, hide_index=True)

# ===========================================================================
# PAGE 2 — REVENUE & GROWTH
# ===========================================================================
elif page == "Revenue & Growth":
    st.title("Revenue & Growth")
    orders = filtered_orders()
    completed = orders[orders["is_recognized"]]
    total_rev = completed["recognized_revenue"].sum()
    n_orders = len(completed)
    aov = completed["net_amount"].mean() if n_orders else 0
    refund_rate = (orders["status"].eq("refunded").sum() / len(orders)) if len(orders) else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(kpi_card("Recognized Revenue", fmt_money(total_rev),
                         f"<span class='section-note'>{len(sel_regions)} regions · "
                         f"{len(sel_plans)} plans</span>"), unsafe_allow_html=True)
    c2.markdown(kpi_card("Completed Orders", f"{n_orders:,}",
                         "<span class='section-note'>within filters</span>"), unsafe_allow_html=True)
    c3.markdown(kpi_card("Avg Order Value", fmt_money(aov),
                         "<span class='section-note'>net of discounts</span>"), unsafe_allow_html=True)
    c4.markdown(kpi_card("Refund Rate", f"{refund_rate*100:.1f}%",
                         "<span class='section-note'>refunded / all orders</span>"),
                unsafe_allow_html=True)

    st.markdown("### Monthly recognized revenue")
    by_month = (completed.groupby("order_month")["recognized_revenue"]
                .sum().reset_index())
    fig = px.bar(by_month, x="order_month", y="recognized_revenue",
                 color_discrete_sequence=[PRIMARY])
    fig.update_layout(template="plotly_dark", height=340,
                      margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      yaxis_title="Revenue ($)", xaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

    a, b = st.columns(2)
    with a:
        st.markdown("#### Revenue by region")
        by_region = (completed.groupby("region")["recognized_revenue"].sum()
                     .sort_values(ascending=False).reset_index())
        fig = px.bar(by_region, x="recognized_revenue", y="region", orientation="h",
                     color="region", color_discrete_sequence=PALETTE)
        fig.update_layout(template="plotly_dark", height=320, showlegend=False,
                          margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                          xaxis_title="Revenue ($)", yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)
    with b:
        st.markdown("#### Revenue by plan")
        by_plan = (completed.groupby("plan")["recognized_revenue"].sum()
                   .reset_index())
        fig = px.pie(by_plan, names="plan", values="recognized_revenue", hole=0.5,
                     color_discrete_sequence=PALETTE)
        fig.update_layout(template="plotly_dark", height=320,
                          margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Revenue by acquisition channel")
    by_ch = (completed.groupby("acquisition_channel")
             .agg(revenue=("recognized_revenue", "sum"),
                  orders=("order_id", "count")).reset_index()
             .sort_values("revenue", ascending=False))
    fig = px.bar(by_ch, x="acquisition_channel", y="revenue", color="acquisition_channel",
                 color_discrete_sequence=PALETTE, text_auto=".2s")
    fig.update_layout(template="plotly_dark", height=320, showlegend=False,
                      margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      yaxis_title="Revenue ($)", xaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# PAGE 3 — CUSTOMER SEGMENTS (the flagship story)
# ===========================================================================
elif page == "Customer Segments":
    st.title("Customer Value Segmentation")
    seg = filtered_segments()
    all_seg = da.customer_segments()

    p_users = all_seg["priority_customer_share"].max() * 100
    p_rev = all_seg["priority_revenue_share"].max() * 100
    st.markdown(
        f"<div class='big-insight'>💡 <b>{p_users:.0f}% of customers → {p_rev:.0f}% of revenue.</b> "
        f"The priority segment is defined once in the warehouse "
        f"(<code>customer_segments.priority_segment</code>) and flows to every tool — "
        f"the single source of truth behind the targeted retention strategy.</div>",
        unsafe_allow_html=True)

    # Tier concentration
    tier = (all_seg.groupby("value_tier")
            .agg(customers=("customer_id", "count"),
                 revenue=("lifetime_revenue", "sum")).reset_index())
    tier_order = ["High-Value", "Core", "Occasional", "Dormant"]
    tier["value_tier"] = pd.Categorical(tier["value_tier"], tier_order, ordered=True)
    tier = tier.sort_values("value_tier")
    tier["cust_share"] = tier["customers"] / tier["customers"].sum()
    tier["rev_share"] = tier["revenue"] / tier["revenue"].sum()

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("#### Revenue vs. customer share by value tier")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=tier["value_tier"], y=tier["cust_share"]*100,
                             name="% of customers", marker_color=SLATE))
        fig.add_trace(go.Bar(x=tier["value_tier"], y=tier["rev_share"]*100,
                             name="% of revenue", marker_color=PRIMARY))
        fig.update_layout(template="plotly_dark", height=360, barmode="group",
                          margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor="rgba(0,0,0,0)",
                          yaxis_title="Share (%)", legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown("#### Pareto: cumulative revenue")
        s = all_seg.sort_values("lifetime_revenue", ascending=False).reset_index(drop=True)
        s["cum_rev"] = s["lifetime_revenue"].cumsum() / s["lifetime_revenue"].sum()
        s["cust_pct"] = (s.index + 1) / len(s)
        fig = px.line(s, x="cust_pct", y="cum_rev", color_discrete_sequence=[GREEN])
        fig.add_vline(x=0.12, line_dash="dot", line_color=AMBER,
                      annotation_text="top 12%")
        fig.add_hline(y=p_rev/100, line_dash="dot", line_color=AMBER)
        fig.update_layout(template="plotly_dark", height=360,
                          margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor="rgba(0,0,0,0)",
                          xaxis_title="Cumulative customers", yaxis_title="Cumulative revenue",
                          xaxis_tickformat=".0%", yaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Tier economics")
    show = tier.copy()
    show["avg_ltv"] = show["revenue"] / show["customers"]
    show = show[["value_tier", "customers", "cust_share", "revenue", "rev_share", "avg_ltv"]]
    show.columns = ["Value tier", "Customers", "% customers", "Lifetime revenue",
                    "% revenue", "Avg lifetime value"]
    st.dataframe(show.style.format({
        "Customers": "{:,.0f}", "% customers": "{:.1%}", "Lifetime revenue": "${:,.0f}",
        "% revenue": "{:.1%}", "Avg lifetime value": "${:,.0f}"}),
        use_container_width=True, hide_index=True)

    # RFM heatmap
    st.markdown("#### RFM distribution (Frequency × Monetary)")
    rfm = (seg.groupby(["f_score", "m_score"])
           .size().reset_index(name="customers"))
    pivot = rfm.pivot(index="m_score", columns="f_score", values="customers").fillna(0)
    fig = px.imshow(pivot, color_continuous_scale="Blues", aspect="auto",
                    labels=dict(x="Frequency score", y="Monetary score", color="Customers"))
    fig.update_layout(template="plotly_dark", height=320,
                      margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Top 25 customers by lifetime value")
    top = (seg.sort_values("lifetime_revenue", ascending=False)
           .head(25)[["customer_name", "region", "plan", "value_tier",
                      "lifetime_orders", "lifetime_revenue", "revenue_share"]])
    top.columns = ["Customer", "Region", "Plan", "Tier", "Orders", "Lifetime rev", "% of total"]
    st.dataframe(top.style.format({
        "Lifetime rev": "${:,.0f}", "% of total": "{:.2%}", "Orders": "{:,.0f}"}),
        use_container_width=True, hide_index=True)

# ===========================================================================
# PAGE 4 — RETENTION & COHORTS
# ===========================================================================
elif page == "Retention & Cohorts":
    st.title("Retention & Cohort Analysis")
    coh = da.cohort_retention()
    km = da.kpi_monthly()

    mature = km[km["cohort_is_mature"] == True]  # noqa: E712
    avg_ret = mature["retention_30d"].mean() if len(mature) else 0
    c1, c2, c3 = st.columns(3)
    c1.markdown(kpi_card("Avg 30-Day Retention", f"{avg_ret*100:.1f}%",
                         "<span class='section-note'>matured cohorts</span>"),
                unsafe_allow_html=True)
    c2.markdown(kpi_card("Avg Monthly Churn", f"{km['churn_rate'].mean()*100:.2f}%",
                         "<span class='section-note'>trailing average</span>"),
                unsafe_allow_html=True)
    subs = da.fct_subscriptions()
    active_share = subs["is_active"].mean()
    c3.markdown(kpi_card("Active Subscriptions", f"{active_share*100:.0f}%",
                         "<span class='section-note'>of all subscriptions</span>"),
                unsafe_allow_html=True)

    st.markdown("### Cohort retention heatmap")
    st.caption("Rows = signup cohort · columns = months since signup · "
               "value = share of the cohort still active (product events).")
    piv = coh.pivot(index="cohort_label", columns="months_since_signup",
                    values="retention_rate")
    piv = piv.sort_index()
    fig = px.imshow(piv, color_continuous_scale="Blues", aspect="auto",
                    labels=dict(x="Months since signup", y="Cohort", color="Retention"),
                    zmin=0, zmax=1)
    fig.update_layout(template="plotly_dark", height=520,
                      margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

    a, b = st.columns(2)
    with a:
        st.markdown("#### Average retention curve")
        curve = coh.groupby("months_since_signup")["retention_rate"].mean().reset_index()
        fig = px.line(curve, x="months_since_signup", y="retention_rate", markers=True,
                      color_discrete_sequence=[PRIMARY])
        fig.update_layout(template="plotly_dark", height=340,
                          margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                          yaxis_tickformat=".0%", xaxis_title="Months since signup",
                          yaxis_title="Retention")
        st.plotly_chart(fig, use_container_width=True)
    with b:
        st.markdown("#### Churn rate by plan")
        churn_plan = (subs.groupby("plan")["is_churned"].mean()
                      .reindex(["Free", "Starter", "Pro", "Business", "Enterprise"])
                      .reset_index())
        fig = px.bar(churn_plan, x="plan", y="is_churned", color="plan",
                     color_discrete_sequence=PALETTE)
        fig.update_layout(template="plotly_dark", height=340, showlegend=False,
                          margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                          yaxis_tickformat=".0%", yaxis_title="Churn rate", xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# PAGE 5 — ACQUISITION & CONVERSION
# ===========================================================================
elif page == "Acquisition & Conversion":
    st.title("Acquisition & Conversion Economics")
    km = da.kpi_monthly()
    sessions = da.q("""
        SELECT channel, count(*) sessions, sum(converted) conversions
        FROM main_staging.stg_web_sessions GROUP BY 1 ORDER BY sessions DESC
    """)
    sessions["conv_rate"] = sessions["conversions"] / sessions["sessions"]

    c1, c2, c3 = st.columns(3)
    tot_sessions = sessions["sessions"].sum()
    tot_conv = sessions["conversions"].sum()
    c1.markdown(kpi_card("Web Sessions", f"{tot_sessions:,.0f}",
                         "<span class='section-note'>all channels</span>"), unsafe_allow_html=True)
    c2.markdown(kpi_card("Conversions", f"{tot_conv:,.0f}",
                         f"<span class='section-note'>{tot_conv/tot_sessions*100:.1f}% blended</span>"),
                unsafe_allow_html=True)
    c3.markdown(kpi_card("Avg CAC", fmt_money(km["cac"].replace(0, np.nan).mean()),
                         "<span class='section-note'>blended trailing</span>"),
                unsafe_allow_html=True)

    st.markdown("### Acquisition funnel")
    tot_pv = int(da.q("SELECT sum(pages_viewed) s FROM main_staging.stg_web_sessions").iloc[0]["s"])
    funnel = pd.DataFrame({
        "stage": ["Page views", "Sessions", "Conversions", "New customers"],
        "value": [tot_pv, int(tot_sessions), int(tot_conv),
                  int(da.q("SELECT count(*) c FROM main_marts.dim_customers").iloc[0]["c"])],
    })
    fig = go.Figure(go.Funnel(y=funnel["stage"], x=funnel["value"],
                              marker_color=PALETTE[:4], textinfo="value+percent initial"))
    fig.update_layout(template="plotly_dark", height=340,
                      margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

    a, b = st.columns(2)
    with a:
        st.markdown("#### Conversion rate by channel")
        fig = px.bar(sessions.sort_values("conv_rate", ascending=False),
                     x="channel", y="conv_rate", color="channel",
                     color_discrete_sequence=PALETTE)
        fig.update_layout(template="plotly_dark", height=340, showlegend=False,
                          margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                          yaxis_tickformat=".1%", yaxis_title="Conversion", xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)
    with b:
        st.markdown("#### Marketing spend by channel × region")
        spend = da.q("""
            SELECT channel, region, sum(spend) spend
            FROM main_staging.stg_marketing_spend GROUP BY 1,2
        """)
        fig = px.bar(spend, x="channel", y="spend", color="region",
                     color_discrete_sequence=PALETTE)
        fig.update_layout(template="plotly_dark", height=340, barmode="stack",
                          margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                          yaxis_title="Spend ($)", xaxis_title=None,
                          legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### CAC vs. LTV over time")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=km["month"], y=km["cac"], name="CAC", line=dict(color=RED)))
    fig.add_trace(go.Scatter(x=km["month"], y=km["ltv"], name="LTV", line=dict(color=GREEN)))
    fig.update_layout(template="plotly_dark", height=320,
                      margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      yaxis_title="$ per customer", legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# PAGE 6 — SELF-SERVE EXPLORER
# ===========================================================================
elif page == "Self-Serve Explorer":
    st.title("Self-Serve Explorer")
    st.markdown("<span class='section-note'>Build your own view against any mart, "
                "or run read-only SQL. Everything is exportable to CSV.</span>",
                unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["No-code pivot", "SQL runner"])

    with tab1:
        table = st.selectbox("Mart table", [
            "kpi_monthly", "kpi_daily", "fct_orders", "fct_subscriptions",
            "dim_customers", "customer_segments", "cohort_retention"])
        df = da.q(f"SELECT * FROM main_marts.{table} LIMIT 100000")
        num_cols = df.select_dtypes("number").columns.tolist()
        cat_cols = [c for c in df.columns if c not in num_cols]

        colA, colB, colC = st.columns(3)
        group_by = colA.selectbox("Group by", ["(none)"] + cat_cols)
        metric = colB.selectbox("Metric", num_cols if num_cols else ["(none)"])
        agg = colC.selectbox("Aggregation", ["sum", "mean", "count", "min", "max"])

        if group_by != "(none)" and metric != "(none)":
            grouped = df.groupby(group_by)[metric].agg(agg).reset_index()
            grouped = grouped.sort_values(metric, ascending=False)
            st.bar_chart(grouped.set_index(group_by), height=340)
            st.dataframe(grouped, use_container_width=True, hide_index=True)
            st.download_button("⬇ Download CSV",
                               grouped.to_csv(index=False).encode("utf-8"),
                               file_name=f"{table}_{group_by}_{metric}_{agg}.csv")
        else:
            st.dataframe(df.head(500), use_container_width=True, hide_index=True)
            st.download_button("⬇ Download CSV (first 500)",
                               df.head(500).to_csv(index=False).encode("utf-8"),
                               file_name=f"{table}.csv")

    with tab2:
        st.caption("Read-only. Only SELECT statements are permitted.")
        default_sql = ("SELECT value_tier, count(*) customers,\n"
                       "       round(sum(lifetime_revenue)) revenue\n"
                       "FROM main_marts.customer_segments\n"
                       "GROUP BY 1 ORDER BY revenue DESC")
        sql = st.text_area("SQL", value=default_sql, height=160)
        if st.button("Run query", type="primary"):
            lowered = sql.strip().lower()
            forbidden = ("insert", "update", "delete", "drop", "create", "alter",
                         "copy", "attach", "pragma", "install", "load")
            if not lowered.startswith("select") or any(f in lowered for f in forbidden):
                st.error("Only single read-only SELECT statements are allowed.")
            else:
                try:
                    res = da.q(sql)
                    st.success(f"{len(res):,} rows")
                    st.dataframe(res, use_container_width=True, hide_index=True)
                    st.download_button("⬇ Download result CSV",
                                       res.to_csv(index=False).encode("utf-8"),
                                       file_name="query_result.csv")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Query error: {exc}")

# Footer
st.markdown("---")
st.caption("Operational Data Warehouse & KPI Dashboard · DuckDB warehouse · dbt "
           "transformations & tests · Streamlit self-serve app · Power BI companion. "
           "Synthetic data, deterministically generated.")
