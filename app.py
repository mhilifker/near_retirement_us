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

# Initialize Master Inputs
if 'steven_age' not in st.session_state: st.session_state.steven_age = 68
if 'ilona_age' not in st.session_state: st.session_state.ilona_age = 67
if 'ret_age' not in st.session_state: st.session_state.ret_age = 70 
if 'downsize_yr' not in st.session_state: st.session_state.downsize_yr = 2031 
if 'inflation_rate' not in st.session_state: st.session_state.inflation_rate = 3.0
if 'usd_market_return' not in st.session_state: st.session_state.usd_market_return = 6.0

# Tax Assumptions (Federal Only)
if 'tax_pretax_base' not in st.session_state: st.session_state.tax_pretax_base = 12.0
if 'tax_pretax_excess' not in st.session_state: st.session_state.tax_pretax_excess = 22.0
if 'tax_cap_gains' not in st.session_state: st.session_state.tax_cap_gains = 15.0
if 'us_ss_tax_rate' not in st.session_state: st.session_state.us_ss_tax_rate = 12.0

# Real Estate Assumptions
if 'home_price' not in st.session_state: st.session_state.home_price = 440000
if 'tax_rate' not in st.session_state: st.session_state.tax_rate = 2.1 
if 'ann_insurance' not in st.session_state: st.session_state.ann_insurance = 2500
if 'ann_apprec' not in st.session_state: st.session_state.ann_apprec = 2.0

# Social Security Macros
if 'steven_ss_age' not in st.session_state: st.session_state.steven_ss_age = 70
if 'steven_future_pct' not in st.session_state: st.session_state.steven_future_pct = 80 
if 'ilona_current_ss' not in st.session_state: st.session_state.ilona_current_ss = 24000 # Default $2k/mo
if 'trust_fund_haircut' not in st.session_state: st.session_state.trust_fund_haircut = 0 
if 'cola_rate' not in st.session_state: st.session_state.cola_rate = 2.1
if 'awi_rate' not in st.session_state: st.session_state.awi_rate = 3.5

# Editable SSA Earnings History for Steven (Constant CAGR from 25k to 110k)
if 'steven_history_df' not in st.session_state:
    start_val = 25000
    end_val = 110000
    years = 45 # 1980 to 2025
    cagr = (end_val / start_val) ** (1 / years) - 1
    earnings_curve = [int(round(start_val * ((1 + cagr) ** i))) for i in range(years + 1)]
    
    st.session_state.steven_history_df = pd.DataFrame({
        "Year": list(range(1980, 2026)),
        "Earnings": earnings_curve
    })

# Spending Targets & Guardrails
if 'spend_active' not in st.session_state: st.session_state.spend_active = 120000
if 'spend_slow' not in st.session_state: st.session_state.spend_slow = 90000
if 'guardrails_enable' not in st.session_state: st.session_state.guardrails_enable = True
if 'floor_active' not in st.session_state: st.session_state.floor_active = 85000
if 'floor_slow' not in st.session_state: st.session_state.floor_slow = 70000
if 'slash_trigger' not in st.session_state: st.session_state.slash_trigger = 5.25
if 'recovery_trigger' not in st.session_state: st.session_state.recovery_trigger = 4.25
if 'raise_pct' not in st.session_state: st.session_state.raise_pct = 33.0

# Stress Testing Macros
if 'sorr_enable' not in st.session_state: st.session_state.sorr_enable = False
if 'sorr_start_yr' not in st.session_state: st.session_state.sorr_start_yr = 2028
if 'sorr_duration' not in st.session_state: st.session_state.sorr_duration = 2
if 'sorr_return' not in st.session_state: st.session_state.sorr_return = -15.0
if 'glide_enable' not in st.session_state: st.session_state.glide_enable = True
if 'glide_start_age' not in st.session_state: st.session_state.glide_start_age = 70
if 'glide_end_age' not in st.session_state: st.session_state.glide_end_age = 85
if 'usd_glide_reduction' not in st.session_state: st.session_state.usd_glide_reduction = 0.1

# Centralized Asset Balances
if 'asset_balances' not in st.session_state:
    st.session_state.asset_balances = {
        "Taxable Brokerage": 100000,
        "Steven: Trad 401(k) / IRA": 500000,
        "Ilona: Trad 401(k) / IRA": 250000,
        "Steven: Roth IRA": 50000,
        "Ilona: Roth IRA": 50000,
        "Cash (Slush Fund)": 40000 
    }

# -----------------------------------------------------------------------------
# CORE SIMULATION ENGINE
# -----------------------------------------------------------------------------
def calculate_person_benefit(history_dict, current_age, ret_age, claim_age, future_pct, cola, haircut, awi):
    current_year = 2026
    working_yrs = max(0, ret_age - current_age)
    age_60_year = current_year + (60 - current_age)
    age_62_year = current_year + (62 - current_age)
    current_max = 176100 
    indexed_earnings = []
    
    for yr, val in history_dict.items():
        if yr < age_60_year:
            idx_factor = (1 + (awi / 100)) ** max(0, age_60_year - yr)
            indexed_earnings.append(val * idx_factor)
        else: indexed_earnings.append(val)
        
    for i in range(working_yrs):
        yr = current_year + i
        projected_max = current_max * ((1 + (awi / 100)) ** (i + 1))
        val = projected_max * (future_pct / 100.0)
        if yr < age_60_year:
            idx_factor = (1 + (awi / 100)) ** (age_60_year - yr)
            indexed_earnings.append(val * idx_factor)
        else: indexed_earnings.append(val)
        
    indexed_earnings.sort(reverse=True)
    top_35 = (indexed_earnings[:35] + [0]*35)[:35]
    aime = sum(top_35) / (35 * 12)
    
    bp_growth_years = max(0, age_62_year - 2026)
    bp_multiplier = (1 + (awi / 100)) ** bp_growth_years
    bp1, bp2 = 1226 * bp_multiplier, 7395 * bp_multiplier
    
    if aime <= bp1: pia = 0.9 * aime
    elif aime <= bp2: pia = (0.9 * bp1) + 0.32 * (aime - bp1)
    else: pia = (0.9 * bp1) + 0.32 * (bp2 - bp1) + 0.15 * (aime - bp2)
    
    mult = 1.0
    if claim_age > 67: mult += (claim_age - 67) * 0.08
    elif claim_age < 67: mult -= (67 - claim_age) * 0.0667
    
    cola_years_before_claim = max(0, claim_age - max(62, current_age))
    cola_multiplier = (1 + (cola / 100)) ** cola_years_before_claim
    annual_at_claim = pia * 12 * mult * cola_multiplier * (1 - (haircut / 100))
    
    timeline = {}
    claim_year = current_year + (claim_age - current_age)
    for yr in range(2026, 2090):
        if yr < claim_year: timeline[yr] = 0
        else: timeline[yr] = annual_at_claim * ((1 + (cola / 100)) ** (yr - claim_year))
    return timeline

def get_ss_timelines():
    steven_history_dict = dict(zip(st.session_state.steven_history_df["Year"], st.session_state.steven_history_df["Earnings"]))
    steven_ss = calculate_person_benefit(
        steven_history_dict, st.session_state.steven_age, st.session_state.ret_age, 
        st.session_state.steven_ss_age, st.session_state.steven_future_pct, 
        st.session_state.cola_rate, st.session_state.trust_fund_haircut, st.session_state.awi_rate
    )
    ilona_ss = {yr: st.session_state.ilona_current_ss * ((1 + (st.session_state.cola_rate / 100)) ** (yr - 2026)) for yr in range(2026, 2090)}
    return steven_ss, ilona_ss

def run_core_simulation():
    STEVEN_SS, ILONA_SS = get_ss_timelines()
    ret_yr = 2026 + (st.session_state.ret_age - st.session_state.steven_age)
    
    current_balances = st.session_state.asset_balances.copy()
    bal_matrix, draw_matrix, tax_matrix, wr_matrix = {}, {}, {}, {}
    asset_rows = list(current_balances.keys())
    
    spend_level = 1.0 
    
    for yr in range(2026, 2090):
        steven_current_age = st.session_state.steven_age + (yr - 2026)
        
        usd_yr_return = st.session_state.usd_market_return / 100.0
        i_rate = st.session_state.inflation_rate / 100.0
        
        # Institutional Stress Tests: Glide Path & SORR
        if st.session_state.glide_enable and steven_current_age >= st.session_state.glide_start_age:
            years_in_glide = min(steven_current_age, st.session_state.glide_end_age) - st.session_state.glide_start_age + 1
            usd_yr_return -= (years_in_glide * (st.session_state.usd_glide_reduction / 100.0))
            
        if st.session_state.sorr_enable and (st.session_state.sorr_start_yr <= yr < (st.session_state.sorr_start_yr + st.session_state.sorr_duration)):
            usd_yr_return = st.session_state.sorr_return / 100.0

        # Downsize Liquidity Event
        if yr == st.session_state.downsize_yr:
            holding_years = yr - 2026
            end_prop_val = st.session_state.home_price * ((1 + (st.session_state.ann_apprec / 100)) ** holding_years)
            net_proceeds = end_prop_val - (end_prop_val * 0.06) 
            current_balances["Taxable Brokerage"] += net_proceeds

        # Apply Returns
        for asset in current_balances.keys():
            if asset != "Cash (Slush Fund)":
                current_balances[asset] *= (1 + usd_yr_return)
                
        current_portfolio = sum(current_balances.values())
        
        # Phase Targeting
        if steven_current_age < 80:
            base_spend_usd = st.session_state.spend_active
            floor_base_usd = st.session_state.floor_active
        else:
            base_spend_usd = st.session_state.spend_slow
            floor_base_usd = st.session_state.floor_slow
            
        target_lifestyle_usd = base_spend_usd * ((1 + i_rate) ** (yr - 2026))
        floor_usd_inflated = floor_base_usd * ((1 + i_rate) ** (yr - 2026))
        
        ss_s, ss_i = STEVEN_SS.get(yr, 0), ILONA_SS.get(yr, 0)
        gross_ss_usd = ss_s + ss_i
        taxable_ss_usd = gross_ss_usd * 0.85 if gross_ss_usd > 0 else 0.0
        irs_shadow_tax_usd = taxable_ss_usd * (st.session_state.us_ss_tax_rate / 100.0)
        net_ss_usd = gross_ss_usd - irs_shadow_tax_usd
        
        # Guardrails Logic
        current_wr = 0.0
        if current_portfolio > 0:
            eval_lifestyle_draw = max(0, (target_lifestyle_usd * spend_level) - net_ss_usd)
            current_wr = eval_lifestyle_draw / current_portfolio
            
            if st.session_state.guardrails_enable:
                if current_wr > (st.session_state.slash_trigger / 100.0):
                    spend_level = floor_usd_inflated / target_lifestyle_usd
                elif current_wr < (st.session_state.recovery_trigger / 100.0) and spend_level < 1.0:
                    spend_level = min(1.0, spend_level * (1 + (st.session_state.raise_pct / 100.0)))
        else:
            spend_level = 1.0

        actual_lifestyle_usd = target_lifestyle_usd * spend_level
        final_eval_draw = max(0, actual_lifestyle_usd - net_ss_usd)
        wr_matrix[yr] = final_eval_draw / current_portfolio if current_portfolio > 0 else 0.0
        
        remaining_need = final_eval_draw
        draws, taxes = {a: 0.0 for a in asset_rows}, {a: 0.0 for a in asset_rows}
        
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
            std_ded_infl = 32000 * ((1 + i_rate) ** (yr - 2026)) 
            pull_from_asset("Steven: Trad 401(k) / IRA", min(remaining_need, std_ded_infl), 0.0)
            pull_from_asset("Taxable Brokerage", remaining_need, st.session_state.tax_cap_gains / 100.0)
            pull_from_asset("Steven: Trad 401(k) / IRA", remaining_need, st.session_state.tax_pretax_base / 100.0)
            pull_from_asset("Ilona: Trad 401(k) / IRA", remaining_need, st.session_state.tax_pretax_base / 100.0)
            pull_from_asset("Steven: Roth IRA", remaining_need, 0.0)
            pull_from_asset("Ilona: Roth IRA", remaining_need, 0.0)
            pull_from_asset("Cash (Slush Fund)", remaining_need, 0.0)

        total_gross_portfolio = sum(draws.values())
        total_taxes_paid = sum(taxes.values()) + irs_shadow_tax_usd
        
        d_col = draws.copy()
        d_col["Steven SS"] = ss_s
        d_col["Ilona SS"] = ss_i
        d_col["Actual Lifestyle Spend"] = actual_lifestyle_usd
        d_col["Total Gross Drawn"] = total_gross_portfolio + gross_ss_usd
        d_col["IRS Tax on SS"] = -irs_shadow_tax_usd
        d_col["Portfolio Tax"] = -sum(taxes.values())
        d_col["Less: Taxes Paid"] = -total_taxes_paid
        d_col["Net Funded"] = (total_gross_portfolio + gross_ss_usd) - total_taxes_paid
        draw_matrix[yr] = d_col
        
        t_col = {a: (taxes[a] / draws[a] if draws[a] > 0 else 0.0) for a in asset_rows}
        t_col["Weighted Average"] = total_taxes_paid / (total_gross_portfolio + gross_ss_usd) if (total_gross_portfolio + gross_ss_usd) > 0 else 0
        tax_matrix[yr] = t_col
        
        b_col = current_balances.copy()
        b_col["Total Portfolio Balance"] = sum(current_balances.values())
        bal_matrix[yr] = b_col

    return pd.DataFrame(bal_matrix), pd.DataFrame(draw_matrix), pd.DataFrame(tax_matrix), pd.Series(wr_matrix)

# -----------------------------------------------------------------------------
# PAGE ROUTING & SIDEBAR
# -----------------------------------------------------------------------------
st.sidebar.title("Navigation")
selection = st.sidebar.radio("Navigate", [
    "1. Executive Dashboard", 
    "2. Pre-Set Asset Ledger & Tax Lots",
    "3. Investment Policy Editor",
    "4. Social Security Determinations", 
    "5. Yearly Cash Flow & Drawdown", 
    "6. Institutional Stress Testing", 
    "7. Longevity Optimizer (Guardrails)"
])

st.sidebar.markdown("---")
st.sidebar.subheader("Quick Stress Scenarios")
if st.sidebar.button("🌿 Baseline (Reset)"):
    st.session_state.sorr_enable = False
    st.session_state.glide_enable = False
if st.sidebar.button("📉 Bear Market"):
    st.session_state.sorr_enable = True
    st.session_state.sorr_start_yr = 2026 + (st.session_state.ret_age - st.session_state.steven_age)
    st.session_state.sorr_duration = 3
    st.session_state.sorr_return = -15.0

# -----------------------------------------------------------------------------
# 1. EXECUTIVE DASHBOARD
# -----------------------------------------------------------------------------
if selection == "1. Executive Dashboard":
    st.header("1. Executive Dashboard")
    c1, c2, c3 = st.columns(3)
    st.session_state.ret_age = c1.number_input("Steven Retirement Age", value=st.session_state.ret_age)
    st.session_state.downsize_yr = c2.number_input("Year to Sell Glenview Home", value=st.session_state.downsize_yr)
    st.session_state.spend_active = c3.number_input("Target Annual Spend (Active Years $)", value=st.session_state.spend_active, step=5000)

    df_bal, df_draw, df_tax, wr_series = run_core_simulation()
    inf_rate = st.session_state.inflation_rate / 100.0

    st.markdown("---")
    zero_years = df_bal.columns[df_bal.loc['Total Portfolio Balance'] <= 0]
    longevity_age = zero_years.min() - 2026 + st.session_state.steven_age if len(zero_years) > 0 else 100
        
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = longevity_age,
        title = {'text': "Projected Portfolio Longevity (Steven's Age)"},
        gauge = {
            'axis': {'range': [st.session_state.steven_age, 100]},
            'bar': {'color': "black", 'thickness': 0.25},
            'steps': [
                {'range': [st.session_state.steven_age, 80], 'color': "rgba(255, 99, 71, 0.8)"},   
                {'range': [80, 90], 'color': "rgba(255, 165, 0, 0.8)"},      
                {'range': [90, 95], 'color': "rgba(255, 235, 59, 0.8)"},     
                {'range': [95, 100], 'color': "rgba(144, 238, 144, 0.8)"}    
            ],
        }
    ))
    fig_gauge.update_layout(height=150, margin=dict(l=50, r=50, t=50, b=10))
    st.plotly_chart(fig_gauge, use_container_width=True)

    st.subheader("Asset Balances Over Time (Nominal)")
    chart_bals = df_bal.drop("Total Portfolio Balance").T
    fig = px.bar(chart_bals, barmode='stack')
    fig.update_layout(xaxis_title="Year", yaxis_title="Balance ($)", legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5, title=""))
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    st.subheader("Yearly Income Sources (Real 2026 $)")
    
    discount_factors_draw = np.array([(1 + inf_rate) ** (yr - 2026) for yr in df_draw.columns])
    df_draw_real = df_draw.div(discount_factors_draw, axis=1)
    
    chart_draws = df_draw_real.T
    
    chart_draws['Brokerage & Cash Draw'] = chart_draws['Taxable Brokerage'] + chart_draws['Cash (Slush Fund)'] + chart_draws['Steven: Roth IRA'] + chart_draws['Ilona: Roth IRA']
    chart_draws['Pre-Tax Draw'] = chart_draws['Steven: Trad 401(k) / IRA'] + chart_draws['Ilona: Trad 401(k) / IRA']
    chart_draws['Social Security'] = chart_draws["Steven SS"] + chart_draws["Ilona SS"]
    
    fig2 = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig2.add_trace(go.Bar(x=chart_draws.index, y=chart_draws['Brokerage & Cash Draw'], name='Brokerage, Roth & Cash Draw'), secondary_y=False)
    fig2.add_trace(go.Bar(x=chart_draws.index, y=chart_draws['Pre-Tax Draw'], name='Pre-Tax Draw'), secondary_y=False)
    fig2.add_trace(go.Bar(x=chart_draws.index, y=chart_draws['Social Security'], name='Social Security'), secondary_y=False)
    
    fig2.add_trace(go.Scatter(
        x=chart_draws.index, 
        y=chart_draws['Actual Lifestyle Spend'], 
        name="Post-Tax Lifestyle Spend", 
        mode='lines+markers', 
        line=dict(color='red', width=3)
    ), secondary_y=False)

    wr_plot_data = wr_series * 100 
    fig2.add_trace(go.Scatter(
        x=wr_plot_data.index,
        y=wr_plot_data.values,
        name="Gross Withdrawal Rate %",
        mode='lines',
        line=dict(color='#00FF00', width=2)
    ), secondary_y=True)
    
    fig2.update_layout(
        barmode='stack',
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5, title=""), 
        hovermode="x unified"
    )
    fig2.update_xaxes(title_text="Year")
    fig2.update_yaxes(title_text="Real Income / Draw (2026 $)", secondary_y=False)
    fig2.update_yaxes(title_text="Withdrawal Rate (%)", secondary_y=True, tickformat='.1f')
    
    st.plotly_chart(fig2, use_container_width=True)

# -----------------------------------------------------------------------------
# 2. PRE-SET ASSET LEDGER & TAX LOTS
# -----------------------------------------------------------------------------
elif selection == "2. Pre-Set Asset Ledger & Tax Lots":
    st.header("2. Pre-Set Asset Ledger & Tax Lots")
    st.markdown("Update current balances to instantly flow through to the entire projection model.")
    
    df_assets = pd.DataFrame(list(st.session_state.asset_balances.items()), columns=["Asset Ledger / Tax Lot", "Current Balance (USD)"])
    edited_df = st.data_editor(df_assets, use_container_width=True, hide_index=True)
    st.session_state.asset_balances = dict(zip(edited_df["Asset Ledger / Tax Lot"], edited_df["Current Balance (USD)"]))

# -----------------------------------------------------------------------------
# 3. INVESTMENT POLICY EDITOR
# -----------------------------------------------------------------------------
elif selection == "3. Investment Policy Editor":
    st.header("3. Investment Policy Editor")
    c1, c2 = st.columns(2)
    st.session_state.inflation_rate = c1.number_input("Annual Inflation (%)", value=st.session_state.inflation_rate, step=0.1)
    st.session_state.usd_market_return = c2.number_input("USD Asset Base Return (%)", value=st.session_state.usd_market_return, step=0.1)
    
    st.markdown("---")
    st.subheader("Tax Assumptions (Federal Only)")
    st.markdown("*Note: Illinois exempts qualified retirement distributions and Social Security from state income tax.*")
    t1, t2, t3, t4 = st.columns(4)
    st.session_state.tax_pretax_base = t1.number_input("Base Pre-Tax Rate (%)", value=st.session_state.tax_pretax_base, step=1.0)
    st.session_state.tax_pretax_excess = t2.number_input("Excess Pre-Tax Rate (%)", value=st.session_state.tax_pretax_excess, step=1.0)
    st.session_state.tax_cap_gains = t3.number_input("Capital Gains Rate (%)", value=st.session_state.tax_cap_gains, step=1.0)
    st.session_state.us_ss_tax_rate = t4.number_input("US SS Tax Rate (%)", value=st.session_state.us_ss_tax_rate, step=1.0)

    st.markdown("---")
    st.subheader("Retirement Phase Lifestyle Targets (Today's 2026 Dollars)")
    r1, r2 = st.columns(2)
    st.session_state.spend_active = r1.number_input("Active Phase (< 80)", value=st.session_state.spend_active, step=5000)
    st.session_state.spend_slow = r2.number_input("Slow Phase (80+)", value=st.session_state.spend_slow, step=5000)

# -----------------------------------------------------------------------------
# 4. SOCIAL SECURITY DETERMINATIONS
# -----------------------------------------------------------------------------
elif selection == "4. Social Security Determinations":
    st.header("4. Actuarial Social Security Engine")
    
    st.sidebar.header("Actuarial Macros")
    st.session_state.awi_rate = st.sidebar.number_input("Average Wage Index (AWI) %", value=st.session_state.awi_rate, step=0.1)
    st.session_state.cola_rate = st.sidebar.number_input("Annual COLA (%)", value=st.session_state.cola_rate, step=0.1)
    st.session_state.trust_fund_haircut = st.sidebar.slider("Trust Fund Haircut (%)", 0, 50, st.session_state.trust_fund_haircut, 5)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Steven's Future Claim")
        st.session_state.steven_ss_age = st.slider("Steven Claim Age", 62, 70, st.session_state.steven_ss_age)
        
        st.markdown("**Steven's Earnings Record**")
        st.markdown("Paste earnings directly from ssa.gov below:")
        edited_history = st.data_editor(st.session_state.steven_history_df, use_container_width=True, hide_index=True, height=400)
        st.session_state.steven_history_df = edited_history

    with c2:
        st.subheader("Ilona's Current Benefit")
        st.markdown("Since Ilona is already claiming, enter her current annual benefit here. It will compound automatically by the COLA rate in future years.")
        st.session_state.ilona_current_ss = st.number_input("Ilona Annual Benefit ($)", value=st.session_state.ilona_current_ss, step=1000)

    STEVEN_SS, ILONA_SS = get_ss_timelines()
    s_claim_yr = 2026 + (st.session_state.steven_ss_age - st.session_state.steven_age)
    
    inf_rate = st.session_state.inflation_rate / 100.0
    s_real_ss = STEVEN_SS[s_claim_yr] / ((1 + inf_rate) ** (s_claim_yr - 2026))
    
    st.markdown("---")
    r1, r2 = st.columns(2)
    r1.success(f"**Steven (Starts {s_claim_yr})**\n\nNominal: **${STEVEN_SS[s_claim_yr]:,.0f}** / yr\n\nReal (2026 $): **${s_real_ss:,.0f}** / yr")
    r2.success(f"**Ilona (Current)**\n\nNominal: **${ILONA_SS[2026]:,.0f}** / yr\n\nReal (2026 $): **${ILONA_SS[2026]:,.0f}** / yr")

# -----------------------------------------------------------------------------
# 5. YEARLY CASH FLOW & DRAWDOWN
# -----------------------------------------------------------------------------
elif selection == "5. Yearly Cash Flow & Drawdown":
    st.header("5. Cash Flow & Tax Engine")
    _, df_draw, df_tax, _ = run_core_simulation()
    
    st.markdown("---")
    st.subheader("Yearly Future Projected Draw (Nominal $)")
    st.dataframe(df_draw.style.format("${:,.0f}"), use_container_width=True, height=400)
    
    st.markdown("---")
    st.subheader("Yearly Future Projected Draw (Real 2026 $)")
    inf_rate = st.session_state.inflation_rate / 100.0
    discount_factors = np.array([(1 + inf_rate) ** (yr - 2026) for yr in df_draw.columns])
    df_draw_real = df_draw.div(discount_factors, axis=1)
    st.dataframe(df_draw_real.style.format("${:,.0f}"), use_container_width=True, height=400)
    
    st.markdown("---")
    st.subheader("Yearly Effective Tax Rate")
    df_tax_t = df_tax.T
    fig_tax = px.line(df_tax_t, y='Weighted Average', markers=True)
    fig_tax.layout.yaxis.tickformat = ',.1%'
    fig_tax.update_layout(xaxis_title="Year", yaxis_title="Effective Tax Rate (%)", showlegend=False)
    st.plotly_chart(fig_tax, use_container_width=True)
    st.dataframe(df_tax.style.format("{:.1%}"), use_container_width=True, height=300)

# -----------------------------------------------------------------------------
# 6. INSTITUTIONAL STRESS TESTING
# -----------------------------------------------------------------------------
elif selection == "6. Institutional Stress Testing":
    st.header("6. Institutional Stress Testing")
    
    st.markdown("---")
    st.subheader("A. Dynamic Asset Allocation (Glide Path)")
    st.markdown("Simulate moving your portfolio from aggressive equities to conservative bonds as you age by dynamically lowering your expected rate of return over time.")
    g1, g2, g3, g4 = st.columns(4)
    st.session_state.glide_enable = g1.toggle("Enable Glide Path", value=st.session_state.glide_enable)
    st.session_state.glide_start_age = g2.number_input("Start De-Risking Age", value=st.session_state.glide_start_age)
    st.session_state.glide_end_age = g3.number_input("End De-Risking Age", value=st.session_state.glide_end_age)
    st.session_state.usd_glide_reduction = g4.number_input("Yearly Reduction in Return (%)", value=st.session_state.usd_glide_reduction, step=0.001, format="%.3f")

    if st.session_state.glide_enable:
        total_usd_drop = (st.session_state.glide_end_age - st.session_state.glide_start_age + 1) * st.session_state.usd_glide_reduction
        st.info(f"**Status:** Active. By age {st.session_state.glide_end_age}, your expected portfolio return will drop from **{st.session_state.usd_market_return:.2f}%** down to **{max(0, st.session_state.usd_market_return - total_usd_drop):.2f}%**.")

    st.markdown("---")
    st.subheader("B. Sequence of Returns Risk (SORR)")
    s1, s2, s3, s4 = st.columns(4)
    st.session_state.sorr_enable = s1.toggle("Enable Market Crash", value=st.session_state.sorr_enable)
    st.session_state.sorr_start_yr = s2.number_input("Crash Start Year", value=st.session_state.sorr_start_yr)
    st.session_state.sorr_duration = s3.number_input("Crash Duration (Years)", value=st.session_state.sorr_duration)
    st.session_state.sorr_return = s4.number_input("Annual Return During Crash (%)", value=st.session_state.sorr_return, step=1.0)

    if st.button("Run Stress Test Diagnostics"):
        with st.spinner("Stress testing portfolio parameters..."):
            df_bal, _, _, _ = run_core_simulation()
            final_yr = 2089
            if final_yr in df_bal.columns and df_bal.loc['Total Portfolio Balance', final_yr] > 0:
                final_val = df_bal.loc['Total Portfolio Balance', final_yr]
                st.success(f"**Test Passed:** Your portfolio survived. Projected nominal terminal wealth at Age 100 is **${final_val / 1000000:,.1f} Million**.")
            else:
                st.error("**Test Failed:** Your portfolio was depleted before age 100 under these stress conditions.")

# -----------------------------------------------------------------------------
# 7. LONGEVITY OPTIMIZER (GUARDRAILS)
# -----------------------------------------------------------------------------
elif selection == "7. Longevity Optimizer (Guardrails)":
    st.header("7. Longevity Optimizer (Guyton-Klinger Guardrails)")
    
    c1, c2 = st.columns(2)
    st.session_state.guardrails_enable = c1.toggle("Enable Dynamic Guardrails", value=st.session_state.guardrails_enable)
    
    st.markdown("---")
    st.subheader("1. The Ironclad Floor (Absolute Minimum Spend in 2026 $)")
    f1, f2 = st.columns(2)
    st.session_state.floor_active = f1.number_input("Active Phase Floor (< 80)", value=st.session_state.floor_active, step=5000)
    st.session_state.floor_slow = f2.number_input("Slow Phase Floor (80+)", value=st.session_state.floor_slow, step=5000)

    st.markdown("---")
    st.subheader("2. Actuarial Triggers")
    t1, t2, t3 = st.columns(3)
    st.session_state.slash_trigger = t1.number_input("Slash Trigger (Withdrawal Rate %)", value=st.session_state.slash_trigger, step=0.1)
    st.session_state.recovery_trigger = t2.number_input("Recovery Trigger (Withdrawal Rate %)", value=st.session_state.recovery_trigger, step=0.1)
    st.session_state.raise_pct = t3.number_input("Annual Recovery Raise (%)", value=st.session_state.raise_pct, step=1.0)
