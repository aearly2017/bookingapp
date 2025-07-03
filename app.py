import streamlit as st
import pandas as pd
from datetime import date
from streamlit_calendar import calendar
from email_utils import send_booking_notification
from PIL import Image
from fpdf import FPDF
import tempfile
import os
from streamlit.components.v1 import html

logo = Image.open("favicon.png")
st.sidebar.image(logo, use_container_width=True)

BOOKINGS_FILE = 'bookings.csv'
PENDING_FILE = 'pending_bookings.csv'
BLOCKED_FILE = 'blocked_dates.csv'

# Ensure CSVs Exist
for file, columns in [
    (BOOKINGS_FILE, ['Name', 'Email', 'Check-in', 'Check-out', 'Notes']),
    (PENDING_FILE, ['Name', 'Email', 'Check-in', 'Check-out', 'Notes']),
    (BLOCKED_FILE, ['Start', 'End'])
]:
    try:
        pd.read_csv(file)
    except:
        pd.DataFrame(columns=columns).to_csv(file, index=False)

def load_bookings(file, date_cols):
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], dayfirst=True, errors='coerce')
    return df

# Admin Login
def check_admin_login():
    if "admin_logged_in" not in st.session_state:
        st.session_state["admin_logged_in"] = False

    if not st.session_state["admin_logged_in"]:
        with st.form("admin_login_form"):
            pw = st.text_input("Admin Password", type="password")
            submitted = st.form_submit_button("Login")
            if submitted:
                if pw == st.secrets["admin"]["password"]:
                    st.session_state["admin_logged_in"] = True
                    st.success("Access granted.")
                    st.rerun()
                else:
                    st.error("Incorrect password.")
        return False
    return True

# Load Data
bookings = load_bookings(BOOKINGS_FILE, ['Check-in', 'Check-out'])
pending = load_bookings(PENDING_FILE, ['Check-in', 'Check-out'])
blocked = load_bookings(BLOCKED_FILE, ['Start', 'End'])

st.set_page_config(page_title="Booking Calendar", layout="centered")
st.header("23 Logan's Beach Availability Calendar")

# Navigation
page = st.sidebar.radio("Navigate", [
    "View Calendar", 
    "Make a Booking Request", 
    "Admin - Approve Requests"
])

# View Calendar
if page == "View Calendar":
    st.markdown("Availability Calendar - Please complete a booking request to apply")
    calendar_events = []

    bookings = load_bookings(BOOKINGS_FILE, ['Check-in', 'Check-out'])  # reload for safety
    pending = load_bookings(PENDING_FILE, ['Check-in', 'Check-out'])
    blocked = load_bookings(BLOCKED_FILE, ['Start', 'End'])

    for _, row in bookings.iterrows():
        if pd.notna(row['Check-in']) and pd.notna(row['Check-out']):
            calendar_events.append({
                "title": "Booked",
                "start": row['Check-in'].strftime('%Y-%m-%d'),
                "end": (row['Check-out'] + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                "color": "green"
            })

    for _, row in pending.iterrows():
        if pd.notna(row['Check-in']) and pd.notna(row['Check-out']):
            calendar_events.append({
                "title": "Tentative",
                "start": row['Check-in'].strftime('%Y-%m-%d'),
                "end": (row['Check-out'] + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                "color": "orange"
            })

    for _, row in blocked.iterrows():
        if pd.notna(row['Start']) and pd.notna(row['End']):
            calendar_events.append({
                "title": "Unavailable",
                "start": row['Start'].strftime('%Y-%m-%d'),
                "end": (row['End'] + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                "color": "gray"
            })

    calendar_options = {"initialView": "dayGridMonth", "height": 600}
    calendar(events=calendar_events, options=calendar_options)

# Booking Request
elif page == "Make a Booking Request":
    st.header("📝 Booking Request Form")

    with st.form("booking_form"):
        name = st.text_input("Name")
        email = st.text_input("Email")
        date_range = st.date_input(
            "Select your stay (Check-in and Check-out)",
            min_value=date.today(),
            value=(date.today(), date.today() + pd.Timedelta(days=1))
        )
        notes = st.text_area("Special Requests / Notes")
        submit = st.form_submit_button("Submit Request")

        if submit:
            if isinstance(date_range, tuple) and len(date_range) == 2:
                check_in = pd.to_datetime(date_range[0])
                check_out = pd.to_datetime(date_range[1])

                if check_out <= check_in:
                    st.error("Check-out must be after check-in.")
                else:
                    conflict = False
                    for df in [bookings, pending]:
                        for _, row in df.iterrows():
                            existing_start = row['Check-in']
                            existing_end = row['Check-out']
                            if pd.isna(existing_start) or pd.isna(existing_end):
                                continue
                            if check_in < existing_end and check_out > existing_start:
                                conflict = True
                                break
                        if conflict:
                            break

                    if conflict:
                        st.error("⚠️ These dates conflict with an existing booking or request.")
                    else:
                        new_request = pd.DataFrame({
                            'Name': [name],
                            'Email': [email],
                            'Check-in': [check_in],
                            'Check-out': [check_out],
                            'Notes': [notes]
                        })

                        pending = pd.concat([pending, new_request], ignore_index=True)
                        pending.to_csv(PENDING_FILE, index=False, date_format='%Y-%m-%d')
                        send_booking_notification(name, email, check_in, check_out, notes)
                        st.success("Your booking request has been submitted!")

# Admin Panel
elif page == "Admin - Approve Requests":
    st.header("🔔 Pending Booking Requests (Admin Only)")

    if not check_admin_login():
        st.stop()

    if pending.empty:
        st.info("No pending booking requests.")
    else:
        for idx, row in pending.iterrows():
            check_in_str = row['Check-in'].strftime('%Y-%m-%d') if pd.notna(row['Check-in']) else 'Unknown'
            check_out_str = row['Check-out'].strftime('%Y-%m-%d') if pd.notna(row['Check-out']) else 'Unknown'

            with st.expander(f"{row['Name']} - {check_in_str} to {check_out_str}"):
                st.write(f"**Email:** {row['Email']}")
                st.write(f"**Notes:** {row['Notes']}")
                col1, col2 = st.columns(2)
                if col1.button(f"✅ Approve Booking {idx}"):
                    # Reload bookings to prevent overwrite
                    current_bookings = load_bookings(BOOKINGS_FILE, ['Check-in', 'Check-out'])
                    current_bookings = pd.concat([current_bookings, pd.DataFrame([row])], ignore_index=True)
                    current_bookings.to_csv(BOOKINGS_FILE, index=False, date_format='%Y-%m-%d')

                    pending.drop(index=idx, inplace=True)
                    pending.to_csv(PENDING_FILE, index=False, date_format='%Y-%m-%d')

                    st.success("Booking approved and added to calendar!")
                    st.rerun()
                if col2.button(f"❌ Delete Booking {idx}"):
                    pending.drop(index=idx, inplace=True)
                    pending.to_csv(PENDING_FILE, index=False, date_format='%Y-%m-%d')
                    st.warning("Booking request deleted.")
                    st.rerun()

    st.markdown("---")
    st.subheader("🖨️ Printable Booking Summary")

    if bookings.empty:
        st.info("No confirmed bookings yet.")
    else:
        with st.expander("📋 View All Confirmed Bookings"):
            for _, row in bookings.iterrows():
                if pd.notna(row['Check-in']) and pd.notna(row['Check-out']):
                    st.write(f"**{row['Name']}**: {row['Check-in'].strftime('%Y-%m-%d')} → {row['Check-out'].strftime('%Y-%m-%d')}")
                else:
                    st.write(f"**{row['Name']}**: (Incomplete date info)")
                if pd.notna(row["Notes"]):
                    st.caption(f"📝 {row['Notes']}")

        if st.button("📄 Download PDF"):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt="Booking Summary", ln=True, align='C')
            pdf.ln(5)

            for _, row in bookings.iterrows():
                if pd.notna(row['Check-in']) and pd.notna(row['Check-out']):
                    line = f"{row['Name']} | {row['Check-in'].strftime('%Y-%m-%d')} to {row['Check-out'].strftime('%Y-%m-%d')}"
                else:
                    line = f"{row['Name']} | (Incomplete date info)"
                pdf.cell(200, 10, txt=line, ln=True)
                if pd.notna(row["Notes"]):
                    pdf.set_font("Arial", size=10)
                    pdf.multi_cell(200, 8, txt=f"Note: {row['Notes']}")
                    pdf.set_font("Arial", size=12)
                pdf.ln(2)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                pdf.output(tmp_file.name)
                st.success("✅ PDF created!")
                st.download_button(
                    label="Download Booking Summary PDF",
                    data=open(tmp_file.name, "rb").read(),
                    file_name="booking_summary.pdf",
                    mime="application/pdf"
                )
