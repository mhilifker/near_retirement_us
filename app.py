import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# -----------------------------------------------------------------------------
# PAGE & SESSION STATE CONFIGURATION
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Glenview Retirement Dashboard", layout="wide")

# Initialize Master Inputs - Parent's Timeline
if 'father_age' not in st.session_state: st.session_state.father_age = 68
if 'mother_age' not in st.session_state: st.session_state.mother_age = 67
if 'ret_age' not in st.session_state: st.session_state.ret_age = 70 # Father's target retirement
if 'downsize_yr' not in st.session_state: st.session_state.downsize_yr = 2031 # 5 years out
if 'inflation_rate' not in st.session_state: st.session_state.inflation_rate = 3.0
if 'usd_market_return' not in st.session_state: st.session_state.usd_market_return = 6.0

# US Tax Assumptions (Federal Only - IL does not tax retirement income)
if 'tax_pretax_base' not in st.session_state: st.session_state.tax_pretax_base = 12.0
if 'tax_pretax_excess' not in st.session_state: st.session_state.tax_pretax_excess = 22.0
if 'tax_cap_gains' not in st.session_state: st.session_state.tax_cap_gains = 15.0
if 'us_ss_tax_rate' not in st.session_state: st.session_state.us_ss_tax_rate = 12.0

# Real Estate Assumptions (Glenview Home)
if 'home_price' not in st.session_state: st.session_state.home_price = 440000
if 'tax_rate' not in st.session_state: st.session_state.tax_rate = 2.1 # IL Property Tax Est
if 'ann_insurance' not in st.session_state: st.session_state.ann_insurance = 2500
if 'ann_apprec' not in st.session_state: st.session_state.ann_apprec = 2.0

# Social Security Claim Ages
if 'father_ss_age' not in st.session_state: st.session_state.father_ss_age = 70
if 'mother_ss_age' not in st.session_state: st.session_state.mother_ss_age = 70
if 'trust_fund_haircut' not in st.session_state: st.session_state.trust_fund_haircut = 0 # Can toggle to 20 for stress test
if 'cola_rate' not in st.session_state: st.session_state.cola_rate = 2.1

# Spending Targets (2026 Dollars) - Placeholder Values
if 'spend_active' not in st.session_state: st.session_state.spend_active = 120000
if 'spend_slow' not in st.session_state: st.session_state.spend_slow = 90000

# Centralized Asset Balances (PLACEHOLDERS PENDING DISCOVERY)
if 'asset_balances' not in st.session_state:
    st.session_state.asset_balances = {
        "Taxable Brokerage": 100000,
        "Father: Trad 401(k) / IRA": 500000,
        "Mother: Trad 401(k) / IRA": 250000,
        "Father: Roth IRA": 50000,
        "Mother: Roth IRA": 50000,
        "Cash (Slush Fund)": 40000 
    }

# -----------------------------------------------------------------------------
# CORE SIMULATION ENGINE (DOMESTIC USD ONLY)
# -----------------------------------------------------------------------------
def run_core_simulation():
    # Placeholder: Assuming simplified flat SS benefit for demonstration since history is unknown
    # In full build, reconnect your calculate_person_benefit function with their actual SS earnings record
    def flat_ss_timeline(claim_age, current_age, base_benefit):
        claim_yr = 2026 + (claim_age - current_age)
        return {yr: (base_benefit * 12 * ((1 + (st.session_state.cola_rate/100))**(yr-2026))) if yr >= claim_yr else 0 for yr in range(2026, 2090)}
    
    FATHER_SS = flat_ss_timeline(st.session_state.father_ss_age, st.session_state.father_age, 3500)
    MOTHER_SS = flat_ss_timeline(st.session_state.mother_ss_age, st.session_state.mother_age, 2000)
    
    ret_yr = 2026 + (st.session_state.ret_age - st.session_state.father_age)
    
    current_balances = st.session_state.asset_balances.copy()
    bal_matrix, draw_matrix, tax_matrix = {}, {}, {}
    
    for yr in range(2026, 2090):
        father_current_age = st.session_state.father_age + (yr - 2026)
        usd_yr_return = st.session_state.usd_market_return / 100.0
        i_rate = st.session_state.inflation_rate / 100.0

        # Downsize Liquidity Event
        if yr == st.session_state.downsize_yr:
            holding_years = yr - 2026
            end_prop_val = st.session_state.home_price * ((1 + (st.session_state.ann_apprec / 100)) ** holding_years)
            net_proceeds = end_prop_val - (end_prop_val * 0.06) # 6% realtor/closing drag
            current_balances["Taxable Brokerage"] += net_proceeds

        # Apply Returns
        for asset in current_balances.keys():
            if asset != "Cash (Slush Fund)":
                current_balances[asset] *= (1 + usd_yr_return)
                
        # Phase Targeting
        base_spend = st.session_state.spend_active if father_current_age < 80 else st.session_state.spend_slow
        target_lifestyle_usd = base_spend * ((1 + i_rate) ** (yr - 2026))
        
        ss_f, ss_m = FATHER_SS.get(yr, 0), MOTHER_SS.get(yr, 0)
        gross_ss_usd = ss_f + ss_m
        irs_shadow_tax_usd = (gross_ss_usd * 0.85) * (st.session_state.us_ss_tax_rate / 100.0) if gross_ss_usd > 0 else 0
        net_ss_usd = gross_ss_usd - irs_shadow_tax_usd
        
        # Drawdown Logic (Simplified for Pre-Tax -> Brokerage -> Roth -> Cash)
        remaining_need = max(0, target_lifestyle_usd - net_ss_usd)
        draws, taxes = {a: 0.0 for a in current_balances.keys()}, {a: 0.0 for a in current_balances.keys()}
        
        def pull_from_asset(asset, amount, tax_rate):
            nonlocal remaining_need
            if remaining_need <= 0 or current_balances[asset] <= 0: return
            gross_needed = min(current_balances[asset], amount / (1 - tax_rate))
            tax_paid = gross_needed * tax_rate
            net_achieved = gross_needed - tax_paid
            current_balances[asset] -= gross_needed
            draws[asset] += gross_needed
            taxes[asset] += tax_paid
            remaining_need -= net_achieved

        if yr >= ret_yr:
            # 1. Drain Standard Deduction Pre-Tax space first (Tax Free)
            std_ded_infl = 32000 * ((1 + i_rate) ** (yr - 2026)) # Joint std deduction approx
            pull_from_asset("Father: Trad 401(k) / IRA", min(remaining_need, std_ded_infl), 0.0)
            
            # 2. Brokerage
            pull_from_asset("Taxable Brokerage", remaining_need, st.session_state.tax_cap_gains / 100.0)
            
            # 3. Excess Pre-Tax
            pull_from_asset("Father: Trad 401(k) / IRA", remaining_need, st.session_state.tax_pretax_base / 100.0)
            pull_from_asset("Mother: Trad 401(k) / IRA", remaining_need, st.session_state.tax_pretax_base / 100.0)
            
            # 4. Roth & Cash
            pull_from_asset("Father: Roth IRA", remaining_need, 0.0)
            pull_from_asset("Mother: Roth IRA", remaining_need, 0.0)
            pull_from_asset("Cash (Slush Fund)", remaining_need, 0.0)

        # Log Data
        total_gross_portfolio = sum(draws.values())
        total_taxes_paid = sum(taxes.values()) + irs_shadow_tax_usd
        
        d_col = draws.copy()
        d_col["Father SS"] = ss_f
        d_col["Mother SS"] = ss_m
        d_col["Net Funded"] = (total_gross_portfolio + gross_ss_usd) - total_taxes_paid
        draw_matrix[yr] = d_col
        
        b_col = current_balances.copy()
        b_col["Total Portfolio Balance"] = sum(current_balances.values())
        bal_matrix[yr] = b_col

    return pd.DataFrame(bal_matrix), pd.DataFrame(draw_matrix)

# -----------------------------------------------------------------------------
# EXECUTIVE DASHBOARD UI
# -----------------------------------------------------------------------------
st.header("Executive Dashboard: Glenview Retirement Plan")
c1, c2, c3 = st.columns(3)
st.session_state.ret_age = c1.number_input("Father Retirement Age", value=st.session_state.ret_age)
st.session_state.downsize_yr = c2.number_input("Year to Sell Glenview Home", value=st.session_state.downsize_yr)
st.session_state.spend_active = c3.number_input("Target Annual Spend (Active Years $)", value=st.session_state.spend_active, step=5000)

df_bal, df_draw = run_core_simulation()

st.markdown("---")
st.subheader("Asset Balances Over Time (Nominal)")
chart_bals = df_bal.drop("Total Portfolio Balance").T
fig = px.bar(chart_bals, barmode='stack', color_discrete_sequence=px.colors.qualitative.Pastel)
fig.update_layout(xaxis_title="Year", yaxis_title="Balance ($)", legend_title="")
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader("Income Draw & Social Security (Nominal)")
chart_draws = df_draw.drop("Net Funded").T
fig2 = px.bar(chart_draws, barmode='stack')
fig2.add_trace(go.Scatter(x=df_draw.columns, y=df_draw.loc["Net Funded"], mode='lines', name="Net Funded", line=dict(color='black', width=3)))
fig2.update_layout(xaxis_title="Year", yaxis_title="Income ($)")
st.plotly_chart(fig2, use_container_width=True)
