import sqlite3
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="LEGO Review Dashboard", layout="wide", page_icon="🧱")

# ---------- Load & prepare data ----------
@st.cache_data
def load_and_prepare_data():
    db_path = "data/lego_reviews.db"
    conn = sqlite3.connect(db_path)
    df_videos = pd.read_sql_query("SELECT * FROM videos", conn)
    df_video_details = pd.read_sql_query("SELECT * FROM video_details", conn)
    df_legosets = pd.read_sql_query("SELECT * FROM legosets", conn)
    conn.close()

    df = pd.merge(df_videos, df_video_details, on="video_id", how="left")
    df = pd.merge(df, df_legosets, left_on="lego_number", right_on="Number", how="left")

    df['upload_date'] = pd.to_datetime(df['upload_date'], errors='coerce')
    df['LaunchDate'] = pd.to_datetime(df['LaunchDate'], errors='coerce')
    int_cols = ['confidence_score', 'views', 'transcript_word_count', 'transcript_char_length']
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
    df['sponsored'] = df['sponsored'].astype(bool)

    filtered = df[
        (df['PackagingType'].str.lower() == 'box') &
        (df['upload_date'] >= pd.Timestamp('2023-01-01')) &
        (df['LaunchDate'].notna()) &
        ((df['LaunchDate'] - df['upload_date']).dt.days <= 183)
    ].copy()

    filtered['upload_week_start'] = filtered['upload_date'] - pd.to_timedelta(filtered['upload_date'].dt.weekday, unit='D')
    filtered['upload_week_label'] = filtered['upload_week_start'].dt.strftime('%Y-W%U')
    filtered['release_year'] = filtered['LaunchDate'].dt.year

    score_map = {
        "strongly negative": 1,
        "slightly negative": 2,
        "slightly positive": 3,
        "strongly positive": 4
    }
    filtered['review_score'] = filtered['review_category'].map(score_map)

    return filtered

df = load_and_prepare_data()

# ---------- Sidebar filters ----------
with st.sidebar:
    st.header("🔍 Filters")
    year_options = sorted(df['release_year'].dropna().unique())
    theme_options = sorted(df['Theme'].dropna().unique())

    selected_years = st.multiselect("📅 Release Year", year_options)
    selected_themes = st.multiselect("🎭 Theme", theme_options)
    sponsored_filter = st.radio("🎁 Sponsorship", ["All", "Only Sponsored", "Only Non-Sponsored"], index=0)

# ---------- Apply filters ----------
filtered_df = df.copy()
if selected_years:
    filtered_df = filtered_df[filtered_df['release_year'].isin(selected_years)]
if selected_themes:
    filtered_df = filtered_df[filtered_df['Theme'].isin(selected_themes)]
if sponsored_filter == "Only Sponsored":
    filtered_df = filtered_df[filtered_df['sponsored'] == True]
elif sponsored_filter == "Only Non-Sponsored":
    filtered_df = filtered_df[filtered_df['sponsored'] == False]

# ---------- Header ----------
st.title("🧱 LEGO Review Dashboard")
st.markdown("""
An interactive portfolio dashboard to analyze LEGO review videos on YouTube.  
Focus: Releases from 2024 & 2025 – Sponsorship, Reach & Rating Trends.
""")
st.markdown("---")

# ---------- KPIs ----------
total_videos = filtered_df['video_id'].nunique()
sponsored_videos = filtered_df[filtered_df['sponsored']].shape[0]
sponsored_pct = round(100 * sponsored_videos / total_videos, 1) if total_videos > 0 else 0

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("📦 Unique LEGO Sets", filtered_df['lego_number'].nunique())
with col2:
    st.metric("📤 Uploaders", filtered_df['uploader'].nunique())
with col3:
    st.markdown(f"""
    <div style='font-size:1.2em;'>🎥 Review Videos</div>
    <div style='font-size:1.5em; font-weight:bold;'>{total_videos:,} <span style='color:red;'>({sponsored_pct}% sponsored)</span></div>
    """, unsafe_allow_html=True)
with col4:
    st.metric("👁️ Total Views", f"{filtered_df['views'].sum():,}")

st.markdown("---")
st.subheader("📆 Timeline of Reviews (on Theme Level)")

# ---------- Timeline Chart ----------
def assign_group(row):
    if row['sponsored']: return "Sponsored"
    elif row['Theme'] == "Ninjago": return "Ninjago"
    elif row['Theme'] == "Star Wars": return "Star Wars"
    else: return "Other"

filtered_df['group'] = filtered_df.apply(assign_group, axis=1)
timeline_data = filtered_df[filtered_df['release_year'].isin([2024, 2025])]
week_order = sorted(timeline_data['upload_week_label'].unique())
df_grouped = timeline_data.groupby(['upload_week_label', 'group']).size().reset_index(name='count')

group_colors = {
    "Sponsored": "red",
    "Ninjago": "#61F47F",
    "Star Wars": "#9D9D9D",
    "Other": "lightgray"
}

fig_timeline = px.bar(
    df_grouped,
    x="upload_week_label",
    y="count",
    color="group",
    color_discrete_map=group_colors,
    category_orders={"upload_week_label": week_order, "group": ["Other", "Star Wars", "Ninjago", "Sponsored"]}
)
fig_timeline.update_layout(
    template="plotly_dark",
    #title=None,
    barmode='stack',
    xaxis_title="Upload Week",
    yaxis_title="Number of Reviews",
    height=450
)
st.plotly_chart(fig_timeline, use_container_width=True)
st.markdown("---")
st.subheader("🎯 Average Rating vs Review Count (on Set Level)")

# ---------- Scatter Plot ----------
set_summary = filtered_df.groupby('lego_number').agg(
    avg_review_score=('review_score', 'mean'),
    review_count=('video_id', 'count'),
    total_views=('views', 'sum'),
    sponsored_any=('sponsored', 'any'),
    SetName=('SetName', 'first'),
    Theme=('Theme', 'first')
).dropna().reset_index()

if set_summary.empty:
    st.warning("⚠️ No data for the current filter selection. Please try a different combination.")
else:
    set_summary['size_scaled'] = set_summary['total_views'].clip(lower=1)
    max_size = set_summary['size_scaled'].max()
    sizeref = 1 if pd.isna(max_size) or max_size == 0 else 2. * max_size / (40. ** 2)
    theme_colors = {'Ninjago': "#61F47F", 'Star Wars': "#9D9D9D"}

    fig = go.Figure()

    for theme in ['Ninjago', 'Star Wars']:
        subset = set_summary[set_summary['Theme'] == theme]
        fig.add_trace(go.Scatter(
            x=subset['review_count'],
            y=subset['avg_review_score'],
            mode='markers+text',
            name=theme,
            text=subset['lego_number'],
            hovertemplate=(
                "Set: %{text}<br>Name: %{customdata[0]}<br>Ø Score: %{y}<br>Reviews: %{x}<br>Views: %{customdata[1]:,}<br>Sponsored: %{customdata[2]}"
            ),
            customdata=subset[['SetName', 'total_views', 'sponsored_any']],
            marker=dict(
                size=subset['size_scaled'],
                sizemode='area',
                sizeref=sizeref,
                sizemin=4,
                color=theme_colors.get(theme, '#999999'),
                line=dict(width=0)
            ),
            textposition='top center'
        ))

    sponsored_sets = set_summary[set_summary['sponsored_any']]
    fig.add_trace(go.Scatter(
        x=sponsored_sets['review_count'],
        y=sponsored_sets['avg_review_score'],
        mode='markers',
        name="Contains Sponsored",
        hoverinfo='skip',
        marker=dict(
            size=sponsored_sets['size_scaled'],
            sizemode='area',
            sizeref=sizeref,
            sizemin=4,
            color='rgba(0,0,0,0)',
            line=dict(width=2, color='red')
        ),
        showlegend=True
    ))

    fig.update_layout(
        template="plotly_dark",
        #title=None,
        xaxis_title="Number of Reviews",
        yaxis_title="Average Review Score (1–4)",
        height=600,
        legend_title="Themes / Sponsorship"
    )

    st.plotly_chart(fig, use_container_width=True)

# ---------- Heatmap: Sponsorship vs. Rating ----------
st.markdown("---")
st.subheader("📤 Sponsorship vs. Average Rating (Uploader Level)")

reliable_uploaders = filtered_df.groupby('uploader').filter(lambda x: len(x) >= 3)

uploader_binned = reliable_uploaders.groupby('uploader').agg(
    avg_score=('review_score', 'mean'),
    sponsored_ratio=('sponsored', 'mean')
).dropna().reset_index()

uploader_binned['sponsored_bin'] = uploader_binned['sponsored_ratio'].apply(
    lambda x: 'sponsored' if x >= 0.1 else 'not sponsored'
)

rating_bins = pd.IntervalIndex.from_tuples([
    (1.0, 1.5), (1.5, 2.0), (2.0, 2.5),
    (2.5, 3.0), (3.0, 3.5), (3.5, 4.0)
], closed='right')

ordered_bin_labels = [f"({a}, {b}]" for a, b in zip(
    [1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
    [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
)]

uploader_binned['score_bin'] = pd.cut(uploader_binned['avg_score'], bins=rating_bins)
uploader_binned['score_bin_label'] = pd.Categorical(
    uploader_binned['score_bin'].astype(str),
    categories=ordered_bin_labels,
    ordered=True
)

heatmap2_data = uploader_binned.groupby(['sponsored_bin', 'score_bin_label']).size().reset_index(name='count')

fig_heatmap2 = px.density_heatmap(
    heatmap2_data,
    x='score_bin_label',
    y='sponsored_bin',
    z='count',
    color_continuous_scale='Reds',
    category_orders={"score_bin_label": ordered_bin_labels}
)
fig_heatmap2.update_layout(
    template="plotly_dark",
    #title=None,
    xaxis_title="Average Rating (Low → High)",
    yaxis_title="Uploader Sponsorship",
    height=450,
    coloraxis_colorbar=dict(title="Uploader Count"),
    xaxis=dict(showticklabels=False)
)
st.plotly_chart(fig_heatmap2, use_container_width=True)

# ---------- Top Critics & Fans ----------
st.markdown("---")

def color_label(category):
    mapping = {
        "strongly positive": '<span style="color: green;">strongly positive</span>',
        "slightly positive": '<span style="color: green;">slightly positive</span>',
        "slightly negative": '<span style="color: red;">slightly negative</span>',
        "strongly negative": '<span style="color: red;">strongly negative</span>',
        None: ''
    }
    return mapping.get(category, category)

review_summaries = filtered_df.groupby(['uploader', 'SetName', 'Theme'])['review_category'].apply(list).reset_index()

def make_expansion_html(uploader):
    rows = review_summaries[review_summaries['uploader'] == uploader]
    items = []
    for _, row in rows.iterrows():
        for cat in row['review_category']:
            label = color_label(cat)
            items.append(f"<li>{row['Theme']} <b>{row['SetName']}</b>: {label}</li>")
    return "<ul style='margin:0; padding-left:16px'>" + "\n".join(items) + "</ul>"

uploader_scores = reliable_uploaders.groupby('uploader').agg(
    avg_score=('review_score', 'mean'),
    video_count=('video_id', 'count'),
    total_views=('views', 'sum'),
    sponsored_ratio=('sponsored', 'mean')
).dropna().reset_index()

def format_sponsoring(ratio):
    if ratio == 0 or pd.isna(ratio):
        return '<span style="color: gray;">not sponsored</span>'
    else:
        percent = int(round(ratio * 100))
        return f'<span style="color: red;"><b>{percent} %</b> sponsored</span>'

uploader_scores['Sponsorship'] = uploader_scores['sponsored_ratio'].apply(format_sponsoring)
uploader_scores['DetailsHTML'] = uploader_scores['uploader'].apply(make_expansion_html)

top_fans = uploader_scores.sort_values(by=['avg_score', 'total_views'], ascending=[False, False]).head(10)
top_critics = uploader_scores.sort_values(by=['avg_score', 'total_views'], ascending=[True, False]).head(10)

def render_accordion_table(df):
    rows_html = ""
    for _, row in df.iterrows():
        header = f"""
        <summary style='cursor: pointer; font-weight: bold;'>
            {row["uploader"]} — {row["video_count"]} videos, Avg Score: {row["avg_score"]:.2f}, Views: {row["total_views"]:,}, {row["Sponsorship"]} <span style="float:right; font-weight:normal; color:#888">Show details ▾</span>
        </summary>
        """
        detail = f"<details style='border:1px solid #444; padding:8px; margin-bottom:8px; border-radius:6px;'>{header}{row['DetailsHTML']}</details>"
        rows_html += detail
    return rows_html

col1, col2 = st.columns(2)
with col1:
    st.markdown("### ❤️ Top 10 Fans")
    st.markdown(render_accordion_table(top_fans), unsafe_allow_html=True)
with col2:
    st.markdown("### 💔 Top 10 Critics")
    st.markdown(render_accordion_table(top_critics), unsafe_allow_html=True)
