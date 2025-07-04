import streamlit as st
import pandas as pd
import gspread
from datetime import date
from streamlit_calendar import calendar
from oauth2client.service_account import ServiceAccountCredentials
from email_utils import send_booking_notification
from PIL import Image
from fpdf import FPDF
import tempfile
from streamlit.components.v1 import html

# ---------- Config ---------- #
st.set_page_config(page_title="Booking Calendar", layout="centered")
st.header("23 Logan's Beach Availability Calendar")

logo = Image.open("favicon.png")
st.sidebar.image(logo, use_container_width=True)

# ---------- Google Sheets Setup ---------- #
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_dict(
    st.secrets["gcp_service_account"], scope
)
client = gspread.authorize(credentials)

sheet = client.open("LoganBookings")
bookings_sheet = sheet.worksheet("bookings")
pending_sheet = sheet.worksheet("pending_bookings")
blocked_sheet = sheet.worksheet("blocked_dates")

# ---------- Load Sheets as DataFrames ---------- #
def load_df(ws):
    df = pd.DataFrame(ws.get_all_records())
    for col in df.columns:
        if "date" in col.lower() or col.lower() in ["check-in", "check-out", "start", "end"]:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    return df

bookings = load_df(bookings_sheet)
pending = load_df(pending_sheet)
blocked = load_df(blocked_sheet)

# ---------- Admin Login ---------- #
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

# ---------- Navigation ---------- #
page = st.sidebar.radio("Navigate", [
    "View Calendar",
    "Make a Booking Request",
    "Admin - Approve Requests",
    "Gallery"
])

# ---------- View Calendar ---------- #
if page == "View Calendar":
    st.markdown("Availability Calendar - Please complete a booking request to apply")
    calendar_events = []

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

# ---------- Booking Request ---------- #
elif page == "Make a Booking Request":
    st.header("📝 Booking Request Form")

    with st.form("booking_form"):
        name = st.text_input("Name")
        email = st.text_input("Email")
        date_range = st.date_input("Select your stay (Check-in and Check-out)",
                                   min_value=date.today(),
                                   value=(date.today(), date.today() + pd.Timedelta(days=1)))
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
                            if check_in < row['Check-out'] and check_out > row['Check-in']:
                                conflict = True
                                break
                        if conflict:
                            break

                    if conflict:
                        st.error("⚠️ These dates conflict with an existing booking or request.")
                    else:
                        pending_sheet.append_row([
                            name, email,
                            check_in.strftime('%Y-%m-%d'),
                            check_out.strftime('%Y-%m-%d'),
                            notes
                        ])
                        send_booking_notification(name, email, check_in, check_out, notes)
                        st.success("Your booking request has been submitted!")

# ---------- Admin Panel ---------- #
elif page == "Admin - Approve Requests":
    st.header("🔔 Pending Booking Requests (Admin Only)")

    if not check_admin_login():
        st.stop()

    pending = load_df(pending_sheet)
    bookings = load_df(bookings_sheet)

    if pending.empty:
        st.info("No pending booking requests.")
    else:
        for idx, row in pending.iterrows():
            with st.expander(f"{row['Name']} - {row['Check-in'].strftime('%Y-%m-%d')} to {row['Check-out'].strftime('%Y-%m-%d')}"):
                st.write(f"**Email:** {row['Email']}")
                st.write(f"**Notes:** {row['Notes']}")
                col1, col2 = st.columns(2)
                if col1.button(f"✅ Approve Booking {idx}"):
                    bookings_sheet.append_row([
                        row['Name'], row['Email'],
                        row['Check-in'].strftime('%Y-%m-%d'),
                        row['Check-out'].strftime('%Y-%m-%d'),
                        row['Notes']
                    ])
                    pending_sheet.delete_rows(idx + 2)
                    st.success("Booking approved and added to calendar!")
                    st.rerun()
                if col2.button(f"❌ Delete Booking {idx}"):
                    pending_sheet.delete_rows(idx + 2)
                    st.warning("Booking request deleted.")
                    st.rerun()

    # Print PDF summary
    st.markdown("---")
    st.subheader("🖨️ Printable Booking Summary")
    if bookings.empty:
        st.info("No confirmed bookings yet.")
    else:
        with st.expander("📋 View All Confirmed Bookings"):
            for _, row in bookings.iterrows():
                st.write(f"**{row['Name']}**: {row['Check-in'].strftime('%Y-%m-%d')} → {row['Check-out'].strftime('%Y-%m-%d')}")
                if pd.notna(row["Notes"]):
                    st.caption(f"📝 {row['Notes']}")

        if st.button("📄 Download PDF"):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt="Booking Summary", ln=True, align='C')
            pdf.ln(5)

            for _, row in bookings.iterrows():
                line = f"{row['Name']} | {row['Check-in'].strftime('%Y-%m-%d')} to {row['Check-out'].strftime('%Y-%m-%d')}"
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

# ---------- Gallery Page ---------- #
elif page == "Gallery":
    st.header("🏡 Logan's Beach Photo Gallery")
    image_folder = "images"
    if os.path.isdir(image_folder):
        image_files = [f for f in os.listdir(image_folder) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
        image_tags = "".join([
            f'<div class="swiper-slide"><img src="/{image_folder}/{img}" style="width:100%;border-radius:10px;"/></div>'
            for img in image_files
        ])

        html(f'''
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.css" />
        <style>.swiper{{width:100%;height:500px;}}.swiper-slide img{{object-fit:cover;height:100%;}}</style>
        <div class="swiper">
          <div class="swiper-wrapper">{image_tags}</div>
          <div class="swiper-pagination"></div>
          <div class="swiper-button-prev"></div>
          <div class="swiper-button-next"></div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.js"></script>
        <script>
        new Swiper('.swiper', {{loop:true,pagination:{{el:'.swiper-pagination'}},navigation:{{nextEl:'.swiper-button-next',prevEl:'.swiper-button-prev'}}}});
        </script>
        ''', height=550)
    else:
        st.warning("No image folder found. Please ensure 'images' exists.")
