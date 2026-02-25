import streamlit as st
import pandas as pd
import json, os
from io import BytesIO

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="Performance Dashboard", layout="wide")
st.title("📊 Performance Dashboard")
st.markdown("---")

S_FILE = "sla_settings.json"

def save_s(d):
    with open(S_FILE, "w") as f:
        json.dump(d, f)

def load_s():
    return json.load(open(S_FILE, "r")) if os.path.exists(S_FILE) else {}

# ---------------- SIDEBAR ----------------
st.sidebar.markdown("### 👽 Upload CSV Files")
st.sidebar.markdown("---")

ups = st.sidebar.file_uploader("", accept_multiple_files=True)
def_sla = st.sidebar.number_input("Default SLA (Seconds)", value=2.0)

# ---------------- MAIN ----------------
if ups and len(ups) >= 2:

    dfs = {}
    for f in ups:
        t = pd.read_csv(f)
        t.columns = t.columns.str.strip()

        nm = next((c for c in ['Transaction Name','Name'] if c in t.columns), None)
        pt = next((c for c in ['90 percentile','90 Percentile'] if c in t.columns), None)
        ps = next((c for c in ['Pass','Passed'] if c in t.columns), 'Pass')
        fl = next((c for c in ['Fail','Failed'] if c in t.columns), 'Fail')

        if nm and pt:
            t = t[[nm, pt, ps, fl]].rename(
                columns={nm:'Txn', pt:'ResponseTime', ps:'Pass', fl:'Fail'}
            )
            t['ResponseTime'] = pd.to_numeric(t['ResponseTime'], errors='coerce').fillna(0)
            dfs[f.name.replace(".csv","")] = t

    run_names = list(dfs.keys())

    col1, col2 = st.columns(2)

    with col1:
        run1_name = st.selectbox("Select Run 1", run_names, index=0)

    with col2:
        run2_name = st.selectbox("Select Run 2", run_names, index=1)

    if run1_name != run2_name:

        run1 = dfs[run1_name][['Txn','ResponseTime']].rename(
            columns={'ResponseTime':'Run1_ResponseTime'}
        )

        run2 = dfs[run2_name].rename(
            columns={
                'ResponseTime':'Run2_ResponseTime',
                'Pass':'Run2_Pass',
                'Fail':'Run2_Fail'
            }
        )

        master = pd.merge(run1, run2, on='Txn', how='inner')

        existing_slas = load_s()
        master["SLA"] = master["Txn"].apply(
            lambda t: existing_slas.get(t, def_sla)
        )

        master["%Change"] = (
            (master["Run2_ResponseTime"] - master["Run1_ResponseTime"])
            / master["Run1_ResponseTime"] * 100
        ).fillna(0)

        master["Status"] = master.apply(
            lambda r: "Pass"
            if (r["Run1_ResponseTime"] <= r["SLA"] and
                r["Run2_ResponseTime"] <= r["SLA"])
            else "Fail",
            axis=1
        )

        master = master[[
            "Txn",
            "SLA",
            "Run1_ResponseTime",
            "Run2_ResponseTime",
            "Run2_Pass",
            "Run2_Fail",
            "%Change",
            "Status"
        ]]

        # ---------------- SEARCH ----------------
        search = st.text_input("🔍 Search Transaction")

        if search:
            filtered = master[master["Txn"].str.contains(search, case=False, na=False)]
        else:
            filtered = master

        # ---------------- UI Styling ----------------
        fmt = {
            "SLA":"{:.3f}",
            "Run1_ResponseTime":"{:.3f}",
            "Run2_ResponseTime":"{:.3f}",
            "%Change":"{:.2f}%",
            "Run2_Pass":"{:.0f}",
            "Run2_Fail":"{:.0f}"
        }

        def highlight_change(val):
            if val > 5:
                return "background-color:#ff4b4b;color:white;"
            elif val < -5:
                return "background-color:#00c853;color:white;"
            return ""

        def highlight_status(val):
            if val == "Fail":
                return "background-color:#ff4b4b;color:white;"
            elif val == "Pass":
                return "background-color:#00c853;color:white;"
            return ""

        styled = (
            filtered.style
            .format(fmt)
            .applymap(highlight_change, subset=["%Change"])
            .applymap(highlight_status, subset=["Status"])
        )

        st.dataframe(styled, use_container_width=True)

        # ---------------- SLA EDITOR ----------------
        st.markdown("---")
        with st.expander("⚙️ Edit SLA Targets"):

            updated_slas = {}

            for txn in master["Txn"]:
                updated_slas[txn] = st.number_input(
                    f"SLA for {txn}",
                    value=float(existing_slas.get(txn, def_sla)),
                    step=0.1,
                    format="%.3f",
                    key=f"sla_{txn}"
                )

            if st.button("💾 Save SLA Changes"):
                save_s(updated_slas)
                st.success("SLA values saved successfully!")
                st.rerun()

        # ---------------- FORMATTED EXCEL EXPORT ----------------
        out = BytesIO()

        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            filtered.to_excel(writer, index=False, sheet_name="Performance")

            workbook  = writer.book
            worksheet = writer.sheets["Performance"]

            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#1F4E78',
                'font_color': 'white',
                'border': 1
            })

            red_format = workbook.add_format({
                'bg_color': '#FFC7CE',
                'font_color': '#9C0006'
            })

            green_format = workbook.add_format({
                'bg_color': '#C6EFCE',
                'font_color': '#006100'
            })

            # Header Style
            for col_num, value in enumerate(filtered.columns.values):
                worksheet.write(0, col_num, value, header_format)

            # Auto width
            for i, col in enumerate(filtered.columns):
                col_width = max(filtered[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, col_width)

            row_count = len(filtered)

            sla_col = filtered.columns.get_loc("SLA")
            run1_col = filtered.columns.get_loc("Run1_ResponseTime")
            run2_col = filtered.columns.get_loc("Run2_ResponseTime")
            pct_col = filtered.columns.get_loc("%Change")
            status_col = filtered.columns.get_loc("Status")

            worksheet.conditional_format(
                1, pct_col, row_count, pct_col,
                {'type': 'cell', 'criteria': '>', 'value': 5, 'format': red_format}
            )

            worksheet.conditional_format(
                1, pct_col, row_count, pct_col,
                {'type': 'cell', 'criteria': '<', 'value': -5, 'format': green_format}
            )

            worksheet.conditional_format(
                1, status_col, row_count, status_col,
                {'type': 'text', 'criteria': 'containing',
                 'value': 'Fail', 'format': red_format}
            )

            worksheet.conditional_format(
                1, status_col, row_count, status_col,
                {'type': 'text', 'criteria': 'containing',
                 'value': 'Pass', 'format': green_format}
            )

            worksheet.conditional_format(
                1, run1_col, row_count, run1_col,
                {'type': 'formula', 'criteria': '=C2>$B2', 'format': red_format}
            )

            worksheet.conditional_format(
                1, run2_col, row_count, run2_col,
                {'type': 'formula', 'criteria': '=D2>$B2', 'format': red_format}
            )

        st.download_button(
            "📥 Download Formatted Excel Report",
            out.getvalue(),
            f"Performance_{run1_name}_vs_{run2_name}.xlsx"
        )

    else:
        st.warning("Please select two different runs.")

else:
    st.info("Upload at least 2 CSV files to enable comparison.")
