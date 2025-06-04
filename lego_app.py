import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import timedelta

# Verbindung zur Datenbank im data-Ordner
conn = sqlite3.connect("data/lego_reviews.db")

# Tabellen einlesen
sets_df = pd.read_sql_query("SELECT * FROM legosets", conn)
videos_df = pd.read_sql_query("SELECT * FROM videos", conn)

# Spaltennamen vereinheitlichen
sets_df.columns = [col.lower() for col in sets_df.columns]
videos_df.columns = [col.lower() for col in videos_df.columns]

# Datentypen und Datumsformat
sets_df['number'] = sets_df['number'].astype(str)
videos_df['lego_number'] = videos_df['lego_number'].astype(str)
videos_df['upload_date'] = pd.to_datetime(videos_df['upload_date'], errors='coerce')

# Videos ab 2023
videos_df = videos_df[videos_df['upload_date'].dt.year >= 2023]

# Zeitangaben vorbereiten
videos_df['calendar_week'] = videos_df['upload_date'].dt.isocalendar().week
videos_df['year'] = videos_df['upload_date'].dt.isocalendar().year
videos_df['week_start'] = videos_df['upload_date'].dt.to_period('W').apply(lambda r: r.start_time)

# Merge: Videos + Set-Infos
merged_df = pd.merge(videos_df, sets_df, left_on="lego_number", right_on="number", how="left")

# --- NEU: Upload-Datum darf max. 6 Monate vor Set-Release-Jahr sein ---
merged_df['release_reference_date'] = pd.to_datetime(merged_df['yearfrom'].astype(str) + '-01-01', errors='coerce')
merged_df = merged_df[
    (merged_df['upload_date'] >= (merged_df['release_reference_date'] - pd.Timedelta(days=183)))
]

# --- Filter Optionen vorbereiten ---
all_sets = merged_df['setname'].dropna().unique()
all_themes = merged_df['theme'].dropna().unique()
all_years = merged_df['yearfrom'].dropna().unique()
all_uploaders = merged_df['uploader'].dropna().unique()

# --- Sidebar Filter: Reihenfolge und ohne Vorauswahl ---
st.sidebar.header("Filter")

# Theme
select_all_themes = st.sidebar.checkbox("Select All Themes", value=False)
selected_themes = st.sidebar.multiselect(
    "Select Themes", sorted(all_themes), default=all_themes if select_all_themes else [])

# Release Year
select_all_years = st.sidebar.checkbox("Select All Years", value=False)
selected_years = st.sidebar.multiselect(
    "Select Release Years", sorted(all_years), default=all_years if select_all_years else [])

# LEGO Sets
select_all_sets = st.sidebar.checkbox("Select All LEGO Sets", value=False)
selected_sets = st.sidebar.multiselect(
    "Select LEGO Sets", sorted(all_sets), default=all_sets if select_all_sets else [])

# Youtuber
select_all_uploaders = st.sidebar.checkbox("Select All Youtubers", value=False)
selected_uploaders = st.sidebar.multiselect(
    "Select Youtubers", sorted(all_uploaders), default=all_uploaders if select_all_uploaders else [])

# --- Filter anwenden ---
filtered_df = merged_df.copy()
if selected_themes:
    filtered_df = filtered_df[filtered_df['theme'].isin(selected_themes)]
if selected_years:
    filtered_df = filtered_df[filtered_df['yearfrom'].isin(selected_years)]
if selected_sets:
    filtered_df = filtered_df[filtered_df['setname'].isin(selected_sets)]
if selected_uploaders:
    filtered_df = filtered_df[filtered_df['uploader'].isin(selected_uploaders)]

# --- KPIs ---
num_sets = filtered_df['setname'].nunique()
num_videos = filtered_df.shape[0]
num_uploaders = filtered_df['uploader'].nunique()
total_views = filtered_df['views'].sum()

st.markdown("## LEGO Review Dashboard")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric(label="Number of Legosets", value=num_sets)
kpi2.metric(label="Number of Videos", value=num_videos)
kpi3.metric(label="Number of Youtubers", value=num_uploaders)
kpi4.metric(label="Total Views", value=f"{total_views:,}")



# --- Timeline: Gestapeltes Balkendiagramm nach yearfrom (Set-Release) ---
timeline_df = (
    filtered_df
    .groupby(['week_start', 'yearfrom'])
    .size()
    .reset_index(name='review_count')
    .sort_values('week_start')
)

fig = px.bar(
    timeline_df,
    x='week_start',
    y='review_count',
    color='yearfrom',
    #title="Reviews Posted Over Time (by Set Release Year)",
    labels={
        'week_start': 'Calendar Week Start',
        'review_count': 'Number of Reviews',
        'yearfrom': 'Release Year (Set)'
    }
)

fig.update_layout(
    xaxis=dict(
        tickformat="%b %Y",
        tickangle=-45,
        dtick="M1"
    ),
    barmode='stack',
    bargap=0.1,
    legend_title="Set Release Year"
)

st.markdown("### Timeline of Reviews per Calendar Week")
st.plotly_chart(fig, use_container_width=True)

# --- Tabelle anzeigen ---
with st.expander("📊 Show Review Data Table"):
    st.dataframe(filtered_df[['upload_date', 'title', 'setname', 'theme', 'yearfrom', 'uploader', 'views']])
