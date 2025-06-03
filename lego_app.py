import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import re

# Funktion zur Überprüfung der LEGO-Set-Nummer
def check_lego_set_match(df):
    def find_match(row):
        pattern = r'\b\d{3,7}\b'
        title_matches = re.findall(pattern, str(row["title"]))
        desc_matches = re.findall(pattern, str(row.get("description", "")))
        found_numbers = set(title_matches + desc_matches)
        return not found_numbers or str(row["lego_number"]) in found_numbers
    df["match_found"] = df.apply(find_match, axis=1)
    return df

# Datenbankverbindung und Laden der Tabellen
conn = sqlite3.connect("data/lego_reviews.db")
df_videos = pd.read_sql_query("SELECT * FROM videos", conn)
df_video_details = pd.read_sql_query("SELECT * FROM video_details", conn)
df_legosets = pd.read_sql_query(
    "SELECT * FROM legosets WHERE Number IN (SELECT DISTINCT lego_number FROM videos)",
    conn
)
conn.close()

# Datenaufbereitung
df = df_videos.merge(df_video_details, on="video_id", how="left")
df = df.merge(df_legosets, left_on="lego_number", right_on="Number", how="left")
df["upload_date"] = pd.to_datetime(df["upload_date"], errors="coerce")
df.dropna(subset=["lego_number", "upload_date"], inplace=True)
df = check_lego_set_match(df)
df = df[df["match_found"]]

# Sidebar: LEGO-Filter mit integrierter "Alle auswählen"-Option
st.sidebar.header("Filter")

# 1. LEGO-Sets (Dropdown mit "(Alle auswählen)" als erste Option)
all_lego_sets = sorted(df["lego_number"].dropna().unique())
lego_options = ["(Alle auswählen)"] + all_lego_sets
selected_lego_raw = st.sidebar.multiselect(
    "Select LEGO Sets",
    options=lego_options,
    default=["(Alle auswählen)"],
    format_func=lambda x: str(x),
)
if "(Alle auswählen)" in selected_lego_raw:
    selected_lego_sets = all_lego_sets.copy()
else:
    selected_lego_sets = [x for x in selected_lego_raw if x in all_lego_sets]

# 2. Youtuber (Dropdown ebenfalls mit "(Alle auswählen)", basierend auf LEGO-Auswahl)
if selected_lego_sets:
    df_for_youtuber = df[df["lego_number"].isin(selected_lego_sets)]
else:
    df_for_youtuber = df.copy()

all_youtubers = sorted(df_for_youtuber["uploader"].dropna().unique())
youtuber_options = ["(Alle auswählen)"] + all_youtubers
selected_youtuber_raw = st.sidebar.multiselect(
    "Select Youtubers",
    options=youtuber_options,
    default=["(Alle auswählen)"],
    format_func=lambda x: x,
)
if "(Alle auswählen)" in selected_youtuber_raw:
    selected_youtubers = all_youtubers.copy()
else:
    selected_youtubers = [x for x in selected_youtuber_raw if x in all_youtubers]

# Filter anwenden
filtered_data = df.copy()
if selected_lego_sets:
    filtered_data = filtered_data[filtered_data["lego_number"].isin(selected_lego_sets)]
if selected_youtubers:
    filtered_data = filtered_data[filtered_data["uploader"].isin(selected_youtubers)]

# KPIs horizontal anordnen und "Number of Views" statt "Average Duration"
st.title("LEGO Review Dashboard")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Number of Legosets", filtered_data["lego_number"].nunique())
with col2:
    st.metric("Number of Videos", len(filtered_data))
with col3:
    st.metric("Number of Youtubers", filtered_data["uploader"].nunique())
with col4:
    total_views = int(filtered_data["views"].sum()) if "views" in filtered_data.columns else 0
    st.metric("Number of Views", total_views)

# Aktive Filter – optisch hervorgehoben
with st.container():
    st.markdown(
        """
        <div style="background-color:#262730; padding:1em; border-radius:10px; margin-bottom:1em;">
            <h4 style="color:white;">🎯 Active Filters</h4>
            <ul style="color:white; list-style-type:square; padding-left:1.2em;">
                <li><b>LEGO Sets</b>: {}</li>
                <li><b>Youtubers</b>: {}</li>
            </ul>
        </div>
        """.format(
            ", ".join(map(str, selected_lego_sets)) if selected_lego_sets else "None selected",
            ", ".join(selected_youtubers) if selected_youtubers else "None selected"
        ),
        unsafe_allow_html=True
    )

# Timeline – Gruppierung nach Kalenderwoche im korrekten chronologischen Ablauf
if not filtered_data.empty:
    # ISO-Jahr und ISO-Woche extrahieren
    iso_cal = filtered_data["upload_date"].dt.isocalendar()
    filtered_data["year"] = iso_cal["year"]
    filtered_data["week"] = iso_cal["week"]
    # Montag (Week Start) berechnen
    filtered_data["week_start"] = filtered_data["upload_date"] - pd.to_timedelta(filtered_data["upload_date"].dt.weekday, unit="d")
    # KW-Label im gewünschten Format "KWXX-YY"
    filtered_data["kw_label"] = filtered_data["upload_date"].dt.strftime("KW%V-%y")

    # Gruppieren nach week_start und kw_label
    reviews_timeline = (
        filtered_data
        .groupby(["week_start", "kw_label"])
        .size()
        .reset_index(name="reviews_count")
        .sort_values("week_start")
        .reset_index(drop=True)
    )

    st.subheader("Timeline of Reviews per Calendar Week")
    fig = px.bar(
        reviews_timeline,
        x="week_start",
        y="reviews_count",
        labels={"week_start": "Calendar Week", "reviews_count": "Number of Reviews"},
        title="Reviews Posted Over Time",
        hover_data={"reviews_count": True, "week_start": False}
    )

    # Nur jede 4. Woche als Tick-Label im Format "KWXX-YY"
    reviews_timeline["kw_tick"] = reviews_timeline["week_start"].dt.strftime("KW%V-%y")
    tick_vals = reviews_timeline["week_start"][::4]
    tick_text = reviews_timeline["kw_tick"][::4]

    fig.update_layout(
        xaxis=dict(
            tickmode="array",
            tickvals=tick_vals,
            ticktext=tick_text
        ),
        xaxis_tickangle=-45,
        margin=dict(t=40, b=80)
    )

    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No data available for the selected filters.")

# Tabelle erst anzeigen, wenn der User sie ausklappt
with st.expander("Show Review Data Overview"):
    st.dataframe(filtered_data)
