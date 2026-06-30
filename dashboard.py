import streamlit as st
import pandas as pd
import mysql.connector
import streamlit as st
from streamlit_autorefresh import st_autorefresh


st.set_page_config(page_title="USB Audit Dashboard", layout="wide")
st_autorefresh(interval=2000, key="usb_refresh")


try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="midhani",
        database="usb_monitor",
    )
except mysql.connector.Error as exc:
    st.error(f"Database connection failed: {exc}")
    st.stop()

query = """
SELECT
    id,
    event_time,
    username,
    system_name,
    mac_address,
    drive_letter,
    usb_name,
    device_code,
    event_type,
    duration_seconds
FROM usb_logs
ORDER BY id DESC
"""

try:
    df = pd.read_sql(query, conn)
except mysql.connector.Error as exc:
    st.error(f"Unable to load USB logs: {exc}")
    st.stop()

st.title("USB Monitoring Dashboard")

if df.empty:
    st.info("No USB events have been recorded yet.")
    st.stop()

st.success("Database Connected")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Events", len(df))
col2.metric("USB Insert", len(df[df["event_type"] == "INSERT"]))
col3.metric("USB Remove", len(df[df["event_type"] == "REMOVE"]))
col4.metric("Unique Devices", df["usb_name"].nunique())

st.subheader("Recent Activity")
show_df = df[[
    "id",
    "event_time",
    "username",
    "system_name",
    "mac_address",
    "drive_letter",
    "usb_name",
    "device_code",
    "event_type",
    "duration_seconds",
]].copy()
show_df.columns = [
    "ID",
    "Event Time",
    "Username",
    "System",
    "MAC Address",
    "Drive",
    "USB Name",
    "Device Code",
    "Event",
    "Duration (sec)",
]
st.dataframe(show_df, use_container_width=True, height=600)
# ---------------------
# FILE HASH TRACKING
# ---------------------

st.subheader(
    "Transferred Files (Hash Tracking)"
)


query2 = """

SELECT

event_time,
username,
device_code,
direction,
file_name,
file_size_mb,
sha256

FROM transfer_logs

ORDER BY id DESC

"""


df2 = pd.read_sql_query(
    query2,
    conn
)


if not df2.empty:

    show_df2 = df2[
        [
            "event_time",
            "username",
            "device_code",
            "direction",
            "file_name",
            "file_size_mb",
            "sha256"
        ]
    ]


    show_df2.columns = [

        "Event Time",

        "Username",

        "Device Code",

        "Direction",

        "File Name",

        "Size (MB)",

        "Hash"

    ]


    st.dataframe(

        show_df2,

        use_container_width=True,

        height=400

    )

else:

    st.info(
        "No file transfer data yet"
    )

st.subheader("System Activity Summary")
summary_query = """
SELECT
u.system_name,
u.username,
COUNT(*) AS usb_sessions,
COALESCE(t.pc_to_usb,0) AS pc_to_usb,
COALESCE(t.usb_to_pc,0) AS usb_to_pc,
COALESCE(t.usb_delete,0) AS usb_delete
FROM usb_logs u
LEFT JOIN
(
SELECT
    system_name,
    SUM(direction='PC_TO_USB') AS pc_to_usb,
    SUM(direction='USB_TO_PC') AS usb_to_pc,
    SUM(direction='USB_DELETE') AS usb_delete
FROM transfer_logs
GROUP BY system_name
) t
ON u.system_name=t.system_name
WHERE u.event_type='INSERT'
GROUP BY
u.system_name,
u.username,
t.pc_to_usb,
t.usb_to_pc,
t.usb_delete
"""

summary_df = pd.read_sql(summary_query, conn)
summary_df["File Operations"] = (
summary_df["pc_to_usb"]
+ summary_df["usb_to_pc"]
+ summary_df["usb_delete"]

)

summary_df.columns = [
    "System",
    "Username",
    "USB Sessions",
    "PC → USB",
    "USB → PC",
    "USB Delete",
    "File Operations"
]

st.dataframe(
    summary_df,
    use_container_width=True,
    height=250
)
conn.close()