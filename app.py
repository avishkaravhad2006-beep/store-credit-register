from io import BytesIO
import sqlite3
from contextlib import contextmanager
import pandas as pd
import streamlit as st
from datetime import datetime, timezone, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ================= CONSTANTS =================
PDF_LEFT_MARGIN = 40
PDF_TOP_MARGIN = 40
PDF_BOTTOM_MARGIN = 50
PDF_HEADER_POSITIONS = [40, 110, 230, 300, 360, 430]
MAX_CHARGE_PERCENTAGE = 10.0
MAX_AMOUNT = 1000000.0

# ================= DATABASE CONTEXT MANAGER =================
@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect("store.db", check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()

# ================= DATABASE INITIALIZATION =================
def init_database():
    """Initialize database with proper schema and indices"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            customer_type TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            payment_mode TEXT NOT NULL,
            b_amount REAL DEFAULT 0,
            b_charges REAL DEFAULT 0,
            k_amount REAL DEFAULT 0,
            k_charges REAL DEFAULT 0,
            grand_charges REAL DEFAULT 0,
            remarks TEXT
        )
        """)
        
        # Create indices for better query performance
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_entry_date 
        ON entries(entry_date)
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_customer_name 
        ON entries(customer_name)
        """)
        
        conn.commit()

# ================= PDF GENERATION =================
def generate_pdf(df, report_date):
    """Generate PDF report with error handling"""
    try:
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        y = height - PDF_TOP_MARGIN
        c.setFont("Helvetica-Bold", 14)
        c.drawString(PDF_LEFT_MARGIN, y, f"Store Daily Report - {report_date}")

        y -= 30
        c.setFont("Helvetica", 9)

        headers = ["Time", "Customer", "Mode", "B Amt", "K Amt", "Charges"]
        
        for i, h in enumerate(headers):
            c.drawString(PDF_HEADER_POSITIONS[i], y, h)

        y -= 15
        c.line(PDF_LEFT_MARGIN, y, width - PDF_LEFT_MARGIN, y)
        y -= 15

        for _, r in df.iterrows():
            if y < PDF_BOTTOM_MARGIN:
                c.showPage()
                y = height - PDF_TOP_MARGIN
                c.setFont("Helvetica", 9)

            # FIX: Use correct column names with capital letters
            c.drawString(PDF_HEADER_POSITIONS[0], y, str(r["Time"]))
            c.drawString(PDF_HEADER_POSITIONS[1], y, str(r["Customer"])[:15])
            c.drawString(PDF_HEADER_POSITIONS[2], y, str(r["Mode"]))
            c.drawString(PDF_HEADER_POSITIONS[3], y, f"{r['B Amount']:.2f}")
            c.drawString(PDF_HEADER_POSITIONS[4], y, f"{r['K Amount']:.2f}")
            c.drawString(PDF_HEADER_POSITIONS[5], y, f"{r['Charges']:.2f}")
            y -= 14

        c.save()
        buffer.seek(0)
        return buffer
    except Exception as e:
        st.error(f"Error generating PDF: {str(e)}")
        return None

# ================= VALIDATION =================
def validate_amount(amount, field_name="Amount"):
    """Validate amount input"""
    if amount < 0:
        st.error(f"{field_name} cannot be negative")
        return False
    if amount > MAX_AMOUNT:
        st.error(f"{field_name} exceeds maximum allowed ({MAX_AMOUNT:,.2f})")
        return False
    return True

def validate_charge_percentage(pct, field_name="Charge"):
    """Validate charge percentage"""
    if pct < 0:
        st.error(f"{field_name} percentage cannot be negative")
        return False
    if pct > MAX_CHARGE_PERCENTAGE:
        st.error(f"{field_name} percentage exceeds maximum ({MAX_CHARGE_PERCENTAGE}%)")
        return False
    return True

# ================= SESSION STATE =================
defaults = {
    "customer_name": "",
    "customer_type": "Office",
    "payment_mode": "Cash",
    "remarks": "",
    "b_entries": [{"amount": 0.0, "charge_pct": 0.0}],
    "k_entries": [{"amount": 0.0, "charge_pct": 0.0}],
    "confirm_delete": False,
    "delete_id": None,
    # FIX: Add counter for unique keys
    "b_counter": 1,
    "k_counter": 1,
}

def initialize_session_state():
    """Initialize session state with defaults"""
    for k, v in defaults.items():
        if k not in st.session_state:
            # FIX: Use copy for mutable defaults to avoid reference issues
            if isinstance(v, list):
                st.session_state[k] = [item.copy() for item in v]
            else:
                st.session_state[k] = v

def reset_form():
    """Reset form to default values"""
    st.session_state.customer_name = defaults["customer_name"]
    st.session_state.customer_type = defaults["customer_type"]
    st.session_state.payment_mode = defaults["payment_mode"]
    st.session_state.remarks = defaults["remarks"]
    st.session_state.b_entries = [{"amount": 0.0, "charge_pct": 0.0, "id": 0}]
    st.session_state.k_entries = [{"amount": 0.0, "charge_pct": 0.0, "id": 0}]
    st.session_state.b_counter = 1
    st.session_state.k_counter = 1

# ================= MAIN APP =================
def main():
    st.set_page_config("Store Credit Register", layout="wide")
    
    # Initialize
    init_database()
    initialize_session_state()
    
    st.title("📋 Store Credit Register")
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(IST)
    st.caption(f"Date: {now:%Y-%m-%d} | Time: {now:%H:%M:%S}")

    tab_new, tab_today, tab_all, tab_summary = st.tabs(
        ["➕ New Entry", "📅 Today's Entries", "📄 All Entries (Edit)", "📊 Summary & Export"]
    )

    # ================= NEW ENTRY =================
    with tab_new:
        render_new_entry_tab()

    # ================= TODAY ENTRIES =================
    with tab_today:
        render_today_entries_tab()

    # ================= ALL ENTRIES (EDIT) =================
    with tab_all:
        render_all_entries_tab()

    # ================= SUMMARY =================
    with tab_summary:
        render_summary_tab()   
        
        
def render_new_entry_tab():
    """Render the new entry tab"""
    now = datetime.now()
    st.subheader("📝 New Entry")
    st.radio("Customer Type", ["Office", "Others"], horizontal=True, key="customer_type")
    st.radio("Payment Mode", ["Cash", "UPI"], horizontal=True, key="payment_mode")
    st.text_input("Customer Name *", key="customer_name")

    st.divider()

    # -------- B (भरलेले) --------
    st.subheader("B (भरलेले) - Deposits")
    b_amt = b_chg = 0.0
    
    # FIX: Ensure each entry has a unique ID for stable keys
    for entry in st.session_state.b_entries:
        if "id" not in entry:
            entry["id"] = st.session_state.b_counter
            st.session_state.b_counter += 1
    
    entries_to_remove = []
    for i, e in enumerate(st.session_state.b_entries):
        # FIX: Use unique ID instead of index for keys
        unique_key = e.get("id", i)
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        
        with col1:
            # FIX: Properly bind value to session state entry
            new_amount = st.number_input(
                f"B Amount #{i+1}", 
                min_value=0.0,
                max_value=MAX_AMOUNT,
                step=100.0,
                value=e["amount"],
                key=f"b_amt_{unique_key}"
            )
            e["amount"] = new_amount
        
        with col2:
            new_charge = st.number_input(
                f"Charge % #{i+1}", 
                min_value=0.0, 
                max_value=MAX_CHARGE_PERCENTAGE,
                step=0.1,
                value=e["charge_pct"],
                key=f"b_chg_{unique_key}"
            )
            e["charge_pct"] = new_charge
        
        ch = e["amount"] * e["charge_pct"] / 100
        
        with col3:
            st.metric("Charge", f"₹{ch:.2f}")
        
        with col4:
            if len(st.session_state.b_entries) > 1:
                if st.button("🗑️", key=f"b_del_{unique_key}", help="Remove this entry"):
                    entries_to_remove.append(i)
        
        b_amt += e["amount"]
        b_chg += ch
    
    # FIX: Remove entries after iteration to avoid modification during iteration
    for idx in reversed(entries_to_remove):
        st.session_state.b_entries.pop(idx)
    if entries_to_remove:
        st.rerun()

    col_add, col_total = st.columns([1, 3])
    with col_add:
        if st.button("➕ Add B Entry", use_container_width=True):
            new_entry = {
                "amount": 0.0, 
                "charge_pct": 0.0, 
                "id": st.session_state.b_counter
            }
            st.session_state.b_counter += 1
            st.session_state.b_entries.append(new_entry)
            st.rerun()
    
    with col_total:
        st.info(f"**Total B:** ₹{b_amt:,.2f} | **B Charges:** ₹{b_chg:.2f}")

    st.divider()

    # -------- K (काढलेले) --------
    st.subheader("K (काढलेले) - Withdrawals")
    k_amt = k_chg = 0.0
    
    # FIX: Ensure each entry has a unique ID for stable keys
    for entry in st.session_state.k_entries:
        if "id" not in entry:
            entry["id"] = st.session_state.k_counter
            st.session_state.k_counter += 1
    
    entries_to_remove = []
    for i, e in enumerate(st.session_state.k_entries):
        # FIX: Use unique ID instead of index for keys
        unique_key = e.get("id", i)
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        
        with col1:
            new_amount = st.number_input(
                f"K Amount #{i+1}", 
                min_value=0.0,
                max_value=MAX_AMOUNT,
                step=100.0,
                value=e["amount"],
                key=f"k_amt_{unique_key}"
            )
            e["amount"] = new_amount
        
        with col2:
            new_charge = st.number_input(
                f"Charge % #{i+1}", 
                min_value=0.0,
                max_value=MAX_CHARGE_PERCENTAGE,
                step=0.1,
                value=e["charge_pct"],
                key=f"k_chg_{unique_key}"
            )
            e["charge_pct"] = new_charge
        
        ch = e["amount"] * e["charge_pct"] / 100
        
        with col3:
            st.metric("Charge", f"₹{ch:.2f}")
        
        with col4:
            if len(st.session_state.k_entries) > 1:
                if st.button("🗑️", key=f"k_del_{unique_key}", help="Remove this entry"):
                    entries_to_remove.append(i)
        
        k_amt += e["amount"]
        k_chg += ch
    
    # FIX: Remove entries after iteration
    for idx in reversed(entries_to_remove):
        st.session_state.k_entries.pop(idx)
    if entries_to_remove:
        st.rerun()

    col_add, col_total = st.columns([1, 3])
    with col_add:
        if st.button("➕ Add K Entry", use_container_width=True):
            new_entry = {
                "amount": 0.0, 
                "charge_pct": 0.0, 
                "id": st.session_state.k_counter
            }
            st.session_state.k_counter += 1
            st.session_state.k_entries.append(new_entry)
            st.rerun()
    
    with col_total:
        st.info(f"**Total K:** ₹{k_amt:,.2f} | **K Charges:** ₹{k_chg:.2f}")

    st.divider()
    
    # Summary
    total_charges = b_chg + k_chg
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Grand Total Charges", f"₹{total_charges:.2f}")
    with col2:
        st.metric("Total (B)", f"₹{b_amt:,.2f}")
    with col3:
        st.metric("Total (K)", f"₹{k_amt:,.2f}")
    
    st.text_area("Remarks (Optional)", key="remarks", height=100)

    if st.button("💾 Save Entry", use_container_width=True, type="primary"):
        # Validation
        if not st.session_state.customer_name.strip():
            st.error("❌ Customer name is required")
            st.stop()
        
        # FIX: Validate amounts and charges
        if not validate_amount(b_amt, "Total B Amount"):
            st.stop()
        if not validate_amount(k_amt, "Total K Amount"):
            st.stop()
        
        # Save with error handling
        try:
            with st.spinner("Saving entry..."):
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                    INSERT INTO entries (
                        entry_date, entry_time, customer_type, customer_name, 
                        payment_mode, b_amount, b_charges, k_amount, k_charges,
                        grand_charges, remarks
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        now.strftime("%Y-%m-%d"),
                        now.strftime("%H:%M:%S"),
                        st.session_state.customer_type,
                        st.session_state.customer_name.strip(),
                        st.session_state.payment_mode,
                        b_amt, b_chg, k_amt, k_chg,
                        total_charges,
                        st.session_state.remarks.strip()
                    ))
                    conn.commit()
                    
            st.success("✅ Entry saved successfully!")
            reset_form()
            st.rerun()
            
        except sqlite3.Error as e:
            st.error(f"❌ Database error: {str(e)}")
        except Exception as e:
            st.error(f"❌ Unexpected error: {str(e)}")
            st.stop()


def render_today_entries_tab():
    """Render today's entries tab"""
    st.subheader("📅 Today's Entries")
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    
    try:
        with get_db_connection() as conn:
            df = pd.read_sql_query("""
                SELECT 
                    entry_time as Time,
                    customer_name as Customer,
                    customer_type as Type,
                    payment_mode as Mode,
                    b_amount as "B Amount",
                    k_amount as "K Amount",
                    grand_charges as Charges,
                    remarks as Remarks
                FROM entries 
                WHERE entry_date=? 
                ORDER BY id DESC
            """, conn, params=(today,))
            
            if not df.empty:
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Quick stats
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Entries", len(df))
                with col2:
                    st.metric("Total B", f"₹{df['B Amount'].sum():,.2f}")
                with col3:
                    st.metric("Total Charges", f"₹{df['Charges'].sum():,.2f}")
            else:
                st.info("📭 No entries for today yet")
                
    except Exception as e:
        st.error(f"❌ Error loading entries: {str(e)}")


def render_all_entries_tab():
    """Render all entries editing tab"""
    st.subheader("📄 All Entries - Edit/Delete")

    # FIX: Initialize date inputs outside try block
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("From Date", datetime.now().replace(day=1))
    with col2:
        end_date = st.date_input("To Date", datetime.now())

    try:
        # FIX: Use separate connection for this tab
        with get_db_connection() as conn:
            df_all = pd.read_sql_query("""
                SELECT * FROM entries 
                WHERE entry_date BETWEEN ? AND ?
                ORDER BY entry_date DESC, id DESC
            """, conn, params=(
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d")
            ))
            
            if df_all.empty:
                st.info("📭 No entries found for selected date range")
                st.stop()

            st.dataframe(df_all, use_container_width=True, hide_index=True)
            st.caption(f"Showing {len(df_all)} entries")

            st.divider()
            
            # Edit section
            eid = st.selectbox("Select Entry ID to Edit/Delete", df_all["id"].tolist())
            row = df_all[df_all.id == eid].iloc[0]

            st.info(f"📅 Original Date: {row.entry_date} | Time: {row.entry_time}")
            
            col1, col2 = st.columns(2)
            with col1:
                en = st.text_input("Customer Name", row.customer_name, key="edit_name")
                ct = st.radio("Customer Type", ["Office", "Others"], 
                             index=0 if row.customer_type=="Office" else 1, 
                             key="edit_ct")
            with col2:
                pm = st.radio("Payment Mode", ["Cash", "UPI"], 
                             index=0 if row.payment_mode=="Cash" else 1, 
                             key="edit_pm")
            
            col1, col2 = st.columns(2)
            with col1:
                b_amt = st.number_input("B Amount", value=float(row.b_amount), 
                                       min_value=0.0, max_value=MAX_AMOUNT, key="edit_ba")
                b_chg = st.number_input("B Charges", value=float(row.b_charges), 
                                       min_value=0.0, key="edit_bc")
            with col2:
                k_amt = st.number_input("K Amount", value=float(row.k_amount), 
                                       min_value=0.0, max_value=MAX_AMOUNT, key="edit_ka")
                k_chg = st.number_input("K Charges", value=float(row.k_charges), 
                                       min_value=0.0, key="edit_kc")
            
            st.metric("Total Charges", f"₹{b_chg + k_chg:.2f}")
            rm = st.text_area("Remarks", row.remarks if pd.notna(row.remarks) else "", key="edit_rm")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Update Entry", use_container_width=True, type="primary"):
                    # FIX: Validate before updating
                    if not en.strip():
                        st.error("❌ Customer name is required")
                        st.stop()
                    
                    try:
                        with st.spinner("Updating..."):
                            # FIX: Use new connection for update
                            with get_db_connection() as update_conn:
                                cursor = update_conn.cursor()
                                cursor.execute("""
                                UPDATE entries SET
                                customer_name=?, customer_type=?, payment_mode=?,
                                b_amount=?, b_charges=?,
                                k_amount=?, k_charges=?,
                                grand_charges=?, remarks=?
                                WHERE id=?
                                """, (en, ct, pm, b_amt, b_chg, k_amt, k_chg, 
                                     b_chg + k_chg, rm, eid))
                                update_conn.commit()
                        st.success("✅ Entry updated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Update failed: {str(e)}")

            with col2:
                if not st.session_state.get("confirm_delete", False):
                    if st.button("🗑️ Delete Entry", use_container_width=True):
                        st.session_state.confirm_delete = True
                        st.session_state.delete_id = eid
                        st.rerun()
                else:
                    if st.session_state.delete_id == eid:
                        st.warning("⚠️ Are you sure?")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ Yes, Delete", use_container_width=True):
                                try:
                                    # FIX: Use new connection for delete
                                    with get_db_connection() as delete_conn:
                                        cursor = delete_conn.cursor()
                                        cursor.execute("DELETE FROM entries WHERE id=?", (eid,))
                                        delete_conn.commit()
                                    st.session_state.confirm_delete = False
                                    st.session_state.delete_id = None
                                    st.success("✅ Entry deleted")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Delete failed: {str(e)}")
                        with col_no:
                            if st.button("❌ Cancel", use_container_width=True):
                                st.session_state.confirm_delete = False
                                st.session_state.delete_id = None
                                st.rerun()
                                
    except Exception as e:
        st.error(f"❌ Error loading entries: {str(e)}")
                 
def render_summary_tab():
    now = datetime.now() 
    """Render summary and export tab"""
    st.subheader("📊 Summary & Export")
    
    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        report_date = st.date_input("Report Date", now, key="summary_report_date")
    with col2:
        report_type = st.radio("Report Type", ["Daily", "Date Range"], horizontal=True)
    
    # FIX: Initialize start_date and end_date before conditional logic
    start_date = report_date
    end_date = report_date
    
    if report_type == "Date Range":
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("From Date", now.replace(day=1), key="summary_start_date")
        with col2:
            end_date = st.date_input("To Date", now, key="summary_end_date")
        date_filter = (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        query_condition = "entry_date BETWEEN ? AND ?"
    else:
        date_filter = (report_date.strftime("%Y-%m-%d"),)
        query_condition = "entry_date = ?"

    try:
        with get_db_connection() as conn:
            # Summary statistics
            summary = pd.read_sql_query(f"""
            SELECT 
                COUNT(*) as count,
                SUM(b_amount) as total_b,
                SUM(k_amount) as total_k,
                SUM(grand_charges) as total_charges
            FROM entries 
            WHERE {query_condition}
            """, conn, params=date_filter).iloc[0]

            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("📝 Entries", int(summary['count']))
            col2.metric("📈 Total B", f"₹{summary.total_b or 0:,.2f}")
            col3.metric("📉 Total K", f"₹{summary.total_k or 0:,.2f}")
            col4.metric("💰 Charges", f"₹{summary.total_charges or 0:.2f}")

            st.divider()

            # Breakdown by payment mode
            st.subheader("Payment Mode Breakdown")
            breakdown = pd.read_sql_query(f"""
            SELECT 
                payment_mode,
                COUNT(*) as entries,
                SUM(grand_charges) as charges
            FROM entries 
            WHERE {query_condition}
            GROUP BY payment_mode
            """, conn, params=date_filter)
            
            if not breakdown.empty:
                st.dataframe(breakdown, use_container_width=True, hide_index=True)

            st.divider()

            # Export section
            st.subheader("📥 Export Data")
            
            export_df = pd.read_sql_query(f"""
            SELECT 
                entry_date as Date,
                entry_time as Time,
                customer_name as Customer,
                customer_type as Type,
                payment_mode as Mode,
                b_amount as "B Amount",
                k_amount as "K Amount",
                grand_charges as Charges,
                remarks as Remarks
            FROM entries 
            WHERE {query_condition}
            ORDER BY entry_date DESC, entry_time DESC
            """, conn, params=date_filter)

            if export_df.empty:
                st.info("📭 No data to export")
                st.stop()

            col1, col2 = st.columns(2)
            
            with col1:
                # Excel export
                try:
                    excel_buffer = BytesIO()
                    # FIX: Add proper error handling for Excel export
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        export_df.to_excel(writer, index=False, sheet_name='Entries')
                    excel_buffer.seek(0)
                    
                    filename = f"Store_Report_{date_filter[0]}"
                    if len(date_filter) > 1:
                        filename += f"_to_{date_filter[1]}"
                    
                    st.download_button(
                        "📊 Download Excel",
                        excel_buffer.getvalue(),
                        f"{filename}.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                except ImportError:
                    st.error("❌ openpyxl library not installed. Run: pip install openpyxl")
                except Exception as e:
                    st.error(f"Excel export error: {str(e)}")

            with col2:
                # PDF export
                try:
                    pdf_buffer = generate_pdf(export_df, 
                                             date_filter[0] if len(date_filter) == 1 
                                             else f"{date_filter[0]} to {date_filter[1]}")
                    if pdf_buffer:
                        filename = f"Store_Report_{date_filter[0]}"
                        if len(date_filter) > 1:
                            filename += f"_to_{date_filter[1]}"
                        
                        st.download_button(
                            "📄 Download PDF",
                            pdf_buffer,
                            f"{filename}.pdf",
                            "application/pdf",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"PDF export error: {str(e)}")

    except Exception as e:
        st.error(f"❌ Error generating summary: {str(e)}")


if __name__ == "__main__":

    main()








