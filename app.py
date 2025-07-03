import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
from fpdf import FPDF

# --- FILE PATHS ---
APPROVED_FILE = "bookings.csv"
PENDING_FILE = "pending_bookings.csv"

# --- PAGE SETUP ---
st.set_page_config(page_title="Logan's Beach Booking", page_icon="🏠", layout="centered")

# --- SIDEBAR IMAGE ---
st.sidebar.image("favicon.png", use_container_width=True)
st.sidebar.title("Logan's Beach Booking App")

st.title("🏡 House Booking Calendar & Request Form")

# --- AUTHENTICATION ---
ADMIN_PASSWORD = "admin123"  # Change this to something secure

is_admin = False
with st.sidebar:
    with st.expander("🔐 Admin Login"):
        admin_input = st.text_input("Enter admin password", type="password")
        if admin_input == ADMIN_PASSWORD:
            is_admin = True
            st.success("Admin access granted!")

# --- LOAD BOOKINGS ---
def load_bookings(file_path):
    if os.path.exists(file_path):
        return pd.read_csv(file_path, parse_dates=["Check-in", "Check-out"])
    else:
        return pd.DataFrame(columns=["Name", "Email", "Check-in", "Check-out", "Notes"])

approved_df = load_bookings(APPROVED_FILE)
pending_df = load_bookings(PENDING_FILE)

# --- 📅 AVAILABILITY CALENDAR ---
st.subheader("📅 Availability Calendar")

year = st.selectbox("Select Year", list(range(datetime.now().year, datetime.now().year + 2)))
month = st.selectbox("Select Month", list(range(1, 13)))

# Get booked dates
booked_dates = []
for _, row in approved_df.iterrows():
    start = row["Check-in"].date()
    end = row["Check-out"].date()
    delta = (end - start).days
    for i in range(delta + 1):
        booked_dates.append(start + timedelta(days=i))

# Render calendar
import calendar
from calendar import monthcalendar

cal = calendar.Calendar()
month_matrix = cal.monthdayscalendar(year, month)

st.markdown(f"#### Calendar for {calendar.month_name[month]} {year}")

cal_html = "<table style='border-collapse: collapse;'><tr>"
for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
    cal_html += f"<th style='padding: 8px;'>{day}</th>"
cal_html += "</tr>"

for week in month_matrix:
    cal_html += "<tr>"
    for day in week:
        date_str = f"{year}-{month:02}-{day:02}"
        is_booked = datetime.strptime(date_str, "%Y-%m-%d").date() in booked_dates if day != 0 else False
        cell_color = "#ffcccc" if is_booked else "#f2f2f2"
        cal_html += (
            f"<td style='border: 1px solid #ccc; padding: 8px; background-color:{cell_color}; text-align:center;'>"
            + (str(day) if day != 0 else "")
            + "</td>"
        )
    cal_html += "</tr>"
cal_html += "</table>"

st.markdown(cal_html, unsafe_allow_html=True)

# --- ✏️ BOOKING FORM ---
st.subheader("📝 Booking Request Form")
with st.form("booking_form"):
    name = st.text_input("Name")
    email = st.text_input("Email")
    checkin = st.date_input("Requested Check-in Date", min_value=datetime.now().date())
    checkout = st.date_input("Requested Check-out Date", min_value=checkin + timedelta(days=1))
    notes = st.text_area("Notes (optional)")
    submitted = st.form_submit_button("Submit Request")

    if submitted:
        # Check for overlap with existing bookings
        conflict = False
        for _, row in approved_df.iterrows():
            if (
                pd.Timestamp(checkin) < row["Check-out"]
                and pd.Timestamp(checkout) > row["Check-in"]
            ):
                conflict = True
                break
        if conflict:
            st.error("Sorry, your requested dates overlap with an existing booking.")
        else:
            new_request = pd.DataFrame(
                [[name, email, checkin, checkout, notes]],
                columns=["Name", "Email", "Check-in", "Check-out", "Notes"]
            )
            pending_df = pd.concat([pending_df, new_request], ignore_index=True)
            pending_df.to_csv(PENDING_FILE, index=False)
            st.success("Your request has been submitted for approval!")

# --- 👮 ADMIN VIEW ---
if is_admin:
    st.subheader("⚠️ Pending Booking Requests (Admin Only)")

    if not pending_df.empty:
        for index, row in pending_df.iterrows():
            with st.expander(f"{row['Name']} - {row['Check-in'].date()} to {row['Check-out'].date()}"):
                st.write(f"**Email:** {row['Email']}")
                st.write(f"**Notes:** {row['Notes']}")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✅ Approve Booking {index}", key=f"approve_{index}"):
                        approved_df = pd.concat([approved_df, pd.DataFrame([row])], ignore_index=True)
                        approved_df.to_csv(APPROVED_FILE, index=False)
                        pending_df.drop(index=index, inplace=True)
                        pending_df.to_csv(PENDING_FILE, index=False)
                        st.success("Booking approved!")
                        st.experimental_rerun()
                with col2:
                    if st.button(f"🗑️ Delete Pending {index}", key=f"delete_pending_{index}"):
                        pending_df.drop(index=index, inplace=True)
                        pending_df.to_csv(PENDING_FILE, index=False)
                        st.warning("Pending booking deleted.")
                        st.experimental_rerun()
    else:
        st.info("No pending bookings.")

    # --- ✅ Confirmed Bookings View & Delete ---
    st.subheader("✅ Confirmed Bookings")
    if not approved_df.empty:
        for index, row in approved_df.iterrows():
            with st.expander(f"{row['Name']} - {row['Check-in'].date()} to {row['Check-out'].date()}"):
                st.write(f"**Email:** {row['Email']}")
                st.write(f"**Notes:** {row['Notes']}")
                if st.button(f"🗑️ Delete Confirmed {index}", key=f"delete_confirmed_{index}"):
                    approved_df.drop(index=index, inplace=True)
                    approved_df.to_csv(APPROVED_FILE, index=False)
                    st.warning("Confirmed booking deleted.")
                    st.experimental_rerun()

    # --- 📤 Export Bookings as PDF ---
    st.subheader("📄 Export Confirmed Bookings to PDF")
    if st.button("Generate PDF"):
        if not approved_df.empty:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(200, 10, "Confirmed Bookings", ln=True, align="C")
            pdf.set_font("Arial", size=12)

            for _, row in approved_df.iterrows():
                pdf.cell(200, 10, f"{row['Name']}: {row['Check-in'].date()} → {row['Check-out'].date()}", ln=True)

            pdf.output("confirmed_bookings.pdf")
            with open("confirmed_bookings.pdf", "rb") as f:
                st.download_button("Download PDF", f, file_name="confirmed_bookings.pdf")
        else:
            st.info("No confirmed bookings to export.")
