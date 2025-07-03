import calendar
from datetime import date
import streamlit as st

def render_monthly_calendar(booked_dates, target_year, target_month):
    cal = calendar.Calendar()
    month_days = cal.monthdatescalendar(target_year, target_month)

    st.markdown(f"### Calendar for {calendar.month_name[target_month]} {target_year}")

    table_html = "<table style='border-collapse: collapse; width: 100%; text-align: center;'>"
    table_html += "<tr>" + "".join(f"<th style='border: 1px solid black; padding:4px;'>{day}</th>" for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]) + "</tr>"

    for week in month_days:
        table_html += "<tr>"
        for day in week:
            style = "border: 1px solid black; padding:8px;"
            day_date = day  # This is a datetime.date object

            if day.month != target_month:
                style += "background-color:#f0f0f0;"  # Grey for other months
            elif day_date in booked_dates:
                style += "background-color:#ff9999;"  # Red for booked days
            table_html += f"<td style='{style}'>{day.day}</td>"
        table_html += "</tr>"

    table_html += "</table>"
    st.markdown(table_html, unsafe_allow_html=True)
