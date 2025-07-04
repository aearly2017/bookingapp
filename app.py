import streamlit as st
import pandas as pd
from datetime import date
from streamlit_calendar import calendar
from email_utils import send_booking_notification
from PIL import Image
from fpdf import FPDF
import tempfile
import os
import shutil
from streamlit.components.v1 import html
import gspread
from google.oauth2.service_account import Credentials
import time

# ---------------- Config & Logo ---------------- #
st.set_page_config(page_title="Booking Calendar", layout="centered")
logo = Image.open("favicon.png")
st.sidebar.image(logo, use_container_width=True)

# ---------------- Secrets & Auth ---------------- #
GCP_SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=GCP_SCOPE
)
client = None

# Retry logic for Google Sheets connection
for attempt in range(3):
    try:
        client = gspread.authorize(creds)
        sheet = client.open_by_key("1YIu1al9lKhwKaGEmf6rjXb622tW9W5hhsAFLMi5k6Ak")
        break
    except Exception as e:
        if attempt < 2:
            time.sleep(2)
        else:
            st.error("Failed to connect to Google Sheets. Please try again later.")
            st.stop()

bookings_ws = sheet.worksheet("bookings")
pending_ws = sheet.worksheet("pending")
blocked_ws = sheet.worksheet("blocked")

# ---------------- Helper Functions ---------------- #
def df_from_ws(ws, date_cols):
    df = pd.DataFrame(ws.get_all_records())
    for col in date_cols:
        if col in df:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    return df

def update_ws(ws, df):
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

bookings = df_from_ws(bookings_ws, ['Check-in', 'Check-out'])
pending = df_from_ws(pending_ws, ['Check-in', 'Check-out'])
blocked = df_from_ws(blocked_ws, ['Start', 'End'])

# ---------------- Admin Login ---------------- #
def check_admin_login():
    if "admin_logged_in" not in st.session_state:
        st.session_state["admin_logged_in"] = False

    if not st.session_state["admin_logged_in"]:
        with st.form("admin_login_form"):
            pw = st.text_input("Admin Password", type="password")
            submitted = st.form_submit_button("Login")
            if submitted and pw == st.secrets["admin"]["password"]:
                st.session_state["admin_logged_in"] = True
                st.success("Access granted.")
                st.rerun()
            elif submitted:
                st.error("Incorrect password.")
        return False
    return True

# ---------------- Navigation ---------------- #
st.header("23 Logan's Beach Availability Calendar")
page = st.sidebar.radio("Navigate", [
    "View Calendar", "Make a Booking Request", "Admin - Approve Requests", "Gallery"
])

# ---------------- View Calendar ---------------- #
if page == "View Calendar":
    st.markdown("Availability Calendar - Please complete a booking request to apply")
    events = []

    for _, row in bookings.iterrows():
        if pd.notna(row['Check-in']) and pd.notna(row['Check-out']):
            events.append({
                "title": "Booked",
                "start": row['Check-in'].strftime('%Y-%m-%d'),
                "end": (row['Check-out'] + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                "color": "green"
            })

    for _, row in pending.iterrows():
        if pd.notna(row['Check-in']) and pd.notna(row['Check-out']):
            events.append({
                "title": "Tentative",
                "start": row['Check-in'].strftime('%Y-%m-%d'),
                "end": (row['Check-out'] + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                "color": "orange"
            })

    for _, row in blocked.iterrows():
        if pd.notna(row['Start']) and pd.notna(row['End']):
            events.append({
                "title": "Unavailable",
                "start": row['Start'].strftime('%Y-%m-%d'),
                "end": (row['End'] + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                "color": "gray"
            })

    calendar(events=events, options={"initialView": "dayGridMonth", "height": 600})

# ---------------- Booking Request ---------------- #
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
                check_in, check_out = pd.to_datetime(date_range)
                if check_out <= check_in:
                    st.error("Check-out must be after check-in.")
                else:
                    conflict = any(
                        (check_in < row['Check-out']) and (check_out > row['Check-in'])
                        for df in [bookings, pending] for _, row in df.iterrows()
                        if pd.notna(row['Check-in']) and pd.notna(row['Check-out'])
                    )
                    if conflict:
                        st.error("⚠️ These dates conflict with an existing booking or request.")
                    else:
                        new_row = pd.DataFrame([{
                            'Name': name, 'Email': email, 'Check-in': check_in,
                            'Check-out': check_out, 'Notes': notes
                        }])
                        pending = pd.concat([pending, new_row], ignore_index=True)
                        update_ws(pending_ws, pending)
                        send_booking_notification(name, email, check_in, check_out, notes)
                        st.success("Your booking request has been submitted!")

# ---------------- Admin Approval ---------------- #
elif page == "Admin - Approve Requests":
    st.header("🔔 Pending Booking Requests (Admin Only)")
    if not check_admin_login():
        st.stop()

    if pending.empty:
        st.info("No pending booking requests.")
    else:
        for idx, row in pending.iterrows():
            with st.expander(f"{row['Name']} - {row['Check-in'].date()} to {row['Check-out'].date()}"):
                st.write(f"**Email:** {row['Email']}")
                st.write(f"**Notes:** {row['Notes']}")
                col1, col2 = st.columns(2)
                if col1.button(f"✅ Approve Booking {idx}"):
                    bookings = pd.concat([bookings, pd.DataFrame([row])], ignore_index=True)
                    update_ws(bookings_ws, bookings)
                    pending.drop(index=idx, inplace=True)
                    pending.reset_index(drop=True, inplace=True)
                    update_ws(pending_ws, pending)
                    st.success("Booking approved.")
                    st.rerun()
                if col2.button(f"❌ Delete Booking {idx}"):
                    pending.drop(index=idx, inplace=True)
                    pending.reset_index(drop=True, inplace=True)
                    update_ws(pending_ws, pending)
                    st.warning("Booking request deleted.")
                    st.rerun()

# ---------------- Gallery ---------------- #
elif page == "Gallery":
    st.header("🏡 Logan's Beach Photo Gallery")

    img_urls = [
        "https://i.imgur.com/VoRaO4A.jpeg",
        "https://i.imgur.com/jmDbprk.jpeg",
        "https://i.imgur.com/KRqXiaO.jpeg",
        "https://i.imgur.com/CWjrKET.jpeg",
        "https://i.imgur.com/4KJOGcN.jpeg"
    ]


    slides = ''.join([
        f'<div class="swiper-slide"><img src="{url}" style="width:100%;height:100%;object-fit:cover;border-radius:10px;"></div>'
        for url in drive_image_urls
    ])

    st.components.v1.html(f'''
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.css" />
    <style>.swiper{{width:100%;height:500px;}}.swiper-slide img{{object-fit:cover;height:100%;}}</style>
    <div class="swiper"><div class="swiper-wrapper">{slides}</div>
    <div class="swiper-pagination"></div>
    <div class="swiper-button-prev"></div><div class="swiper-button-next"></div></div>
    <script src="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.js"></script>
    <script>
    new Swiper('.swiper', {{
      loop:true,
      pagination:{{el:'.swiper-pagination'}},
      navigation:{{nextEl:'.swiper-button-next',prevEl:'.swiper-button-prev'}}
    }});
    </script>
    ''', height=550)