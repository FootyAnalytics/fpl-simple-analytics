import streamlit as st
import pandas as pd
import json
import base64
import os
import plotly.graph_objects as go

# =====================================
# Session State Defaults
# =====================================
if "selected_player" not in st.session_state:
    st.session_state.selected_player = "None"
if "selected_player2" not in st.session_state:
    st.session_state.selected_player2 = "None"


# =====================================
# Background Image
# =====================================
def set_background(image_file: str):
    if not os.path.exists(image_file):
        return  # silently skip if missing on cloud
    with open(image_file, "rb") as f:
        data = f.read()
        base64_image = base64.b64encode(data).decode()

    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{base64_image}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            background-repeat: no-repeat;
        }}

        .main-container {{
            background: rgba(255,255,255,0.85);
            padding: 20px;
            border-radius: 15px;
        }}

        .block-container {{
            padding-left: 3rem !important;
            padding-right: 3rem !important;
            max-width: 2000px !important;
        }}

        .row_heading.level0 {{display:none}}
        .blank {{display:none}}
        </style>
        """,
        unsafe_allow_html=True
    )


IMAGE_PATH = "bg1.png"
set_background(IMAGE_PATH)


# =====================================
# Load Local Cache
# =====================================
CACHE_DIR = "cache"
PLAYERS_FILE = os.path.join(CACHE_DIR, "players.json")
WEEKLY_FILE = os.path.join(CACHE_DIR, "weekly.json")


@st.cache_data
def load_players():
    with open(PLAYERS_FILE, "r") as f:
        data = json.load(f)

    df = pd.DataFrame(data["elements"])
    teams = pd.DataFrame(data["teams"])[["id", "name"]].rename(
        columns={"id": "team", "name": "Team"}
    )
    df = df.merge(teams, on="team", how="left")

    # Position
    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    df["Position"] = df["element_type"].map(pos_map)

    # Pricing
    df["Current Price"] = df["now_cost"] / 10

    # Base total points (season-long)
    df["Points Per Million (Season)"] = df["total_points"] / df["Current Price"]

    # Ownership
    df["Selected By (Decimal)"] = pd.to_numeric(df["selected_by_percent"], errors="coerce") / 100
    df["Selected By %"] = df["Selected By (Decimal)"] * 100

    # Template & differential (season-long)
    df["Template Value (Season)"] = df["Points Per Million (Season)"] * df["Selected By (Decimal)"]
    df["Differential Value (Season)"] = df["Points Per Million (Season)"] * (
        1 - df["Selected By (Decimal)"]
    )

    return df


@st.cache_data
def load_weekly():
    with open(WEEKLY_FILE, "r") as f:
        return json.load(f)


players = load_players()
weekly = load_weekly()

# =====================================
# Weekly DF for slider limits
# =====================================
weekly_df = pd.concat([pd.DataFrame(v) for v in weekly.values()], ignore_index=True)
min_gw = int(weekly_df["round"].min())
max_gw = int(weekly_df["round"].max())


# =====================================
# Helper: GW-range total points for table
# =====================================
def get_points_for_range(player_id: int, gw1: int, gw2: int) -> int:
    history = weekly.get(str(player_id), [])
    if not history:
        return 0
    df = pd.DataFrame(history)
    df = df[(df["round"] >= gw1) & (df["round"] <= gw2)]
    return int(df["total_points"].sum())


# =====================================
# SIDEBAR FILTERS (Form only for filters)
# =====================================
with st.sidebar.form("filters_form", clear_on_submit=False):

    st.header("🔍 Filters")

    team_filter = st.selectbox(
        "Team",
        ["All Teams"] + sorted(players["Team"].unique()),
        key="team_filter"
    )

    position_filter = st.selectbox(
        "Position",
        ["All", "GK", "DEF", "MID", "FWD"],
        key="position_filter"
    )

    gw_start, gw_end = st.slider(
        "Gameweek Range",
        min_value=min_gw,
        max_value=max_gw,
        value=(min_gw, max_gw),
        key="gw_slider"
    )

    sort_column = st.selectbox(
        "Sort Table By",
        [
            "Points (GW Range)",
            "Current Price",
            "Points Per Million",
            "Selected By %",
            "Template Value",
            "Differential Value"
        ],
        key="sort_column"
    )

    sort_order = st.radio(
        "Sort Order",
        ["Descending", "Ascending"],
        key="sort_order"
    )

    reset_clicked = st.form_submit_button("🔄 Reset All Filters")

# Handle reset safely
if reset_clicked:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


# =====================================
# PLAYER SELECTION (outside form)
# =====================================
st.sidebar.markdown("---")  # visual divider
st.sidebar.header("👤 Player Analysis")

st.session_state.selected_player = st.sidebar.selectbox(
    "Player A — View / Compare",
    ["None"] + sorted(players["web_name"].unique()),
    key="player_a_select"
)

st.session_state.selected_player2 = st.sidebar.selectbox(
    "Player B — Comparison",
    ["None"] + sorted(players["web_name"].unique()),
    key="player_b_select"
)


# =====================================
# Filter main player table
# =====================================
filtered = players.copy()

if st.session_state.get("team_filter", "All Teams") != "All Teams":
    filtered = filtered[filtered["Team"] == st.session_state.team_filter]

if st.session_state.get("position_filter", "All") != "All":
    filtered = filtered[filtered["Position"] == st.session_state.position_filter]

# Apply GW-range points for table
filtered["Points (GW Range)"] = filtered.apply(
    lambda r: get_points_for_range(r["id"], st.session_state.gw_slider[0], st.session_state.gw_slider[1]),
    axis=1,
)

# Build display table
table = filtered[
    [
        "web_name",
        "Team",
        "Position",
        "Points (GW Range)",
        "Current Price",
        "Selected By %",
    ]
].rename(columns={"web_name": "Player"})

# Recompute value metrics over GW-range
table["Points Per Million"] = table["Points (GW Range)"] / table["Current Price"]

sel_decimal = table["Selected By %"] / 100
table["Template Value"] = table["Points Per Million"] * sel_decimal
table["Differential Value"] = table["Points Per Million"] * (1 - sel_decimal)

# Round display values
round_cols = [
    "Current Price",
    "Points (GW Range)",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value",
]
table[round_cols] = table[round_cols].round(2)

# Sort
ascending = st.session_state.get("sort_order", "Descending") == "Ascending"
table = table.sort_values(by=st.session_state.get("sort_column", "Points (GW Range)"), ascending=ascending)


# =====================================
# Player Breakdown Helper
# =====================================
def build_player_breakdown(web_name: str):
    """
    Returns dict with:
      - name, position
      - has_data
      - history_df (GW-filtered)
      - breakdown_df (FPL points contribution by category)
    """
    row = players[players["web_name"] == web_name]
    if row.empty:
        return {"has_data": False}

    pid = int(row["id"].iloc[0])
    pos = row["Position"].iloc[0]

    history = weekly.get(str(pid), [])
    if not history:
        return {"has_data": False, "name": web_name, "position": pos}

    df = pd.DataFrame(history)
    df = df[
        (df["round"] >= st.session_state.gw_slider[0])
        & (df["round"] <= st.session_state.gw_slider[1])
    ].copy()

    if df.empty:
        return {"has_data": False, "name": web_name, "position": pos}

    # Aggregate raw stats
    mins = df["minutes"].sum()
    goals = df["goals_scored"].sum()
    assists = df["assists"].sum()
    cs = df["clean_sheets"].sum()
    gc = df["goals_conceded"].sum()
    bonus = df["bonus"].sum()
    saves = df["saves"].sum()
    yc = df["yellow_cards"].sum()
    rc = df["red_cards"].sum()
    og = df["own_goals"].sum()
    pens_missed = df["penalties_missed"].sum()
    pens_saved = df["penalties_saved"].sum()
    dc_raw = df.get("defensive_contribution", pd.Series([0] * len(df))).sum()
    total_points = df["total_points"].sum()

    # FPL-ish points by category (keeps what you had working, but grouped nicely)
    # Minutes points: 1 for <=60, 2 for >=60
    minutes_points = 0
    for m in df["minutes"]:
        if m >= 60:
            minutes_points += 2
        elif m > 0:
            minutes_points += 1

    # Goals
    if pos == "GK":
        goal_pts = goals * 10
    elif pos == "DEF":
        goal_pts = goals * 6
    elif pos == "MID":
        goal_pts = goals * 5
    else:  # FWD
        goal_pts = goals * 4

    # Assists
    assist_pts = assists * 3

    # Clean sheets
    if pos in ["GK", "DEF"]:
        cs_pts = cs * 4
    elif pos == "MID":
        cs_pts = cs * 1
    else:
        cs_pts = 0

    # Saves (GK)
    save_pts = (saves // 3) * 1 if pos == "GK" else 0

    # Goals conceded (GK/DEF)
    gc_pts = 0
    if pos in ["GK", "DEF"]:
        gc_pts = -1 * (gc // 2)

    # Cards & discipline
    yc_pts = -1 * yc
    rc_pts = -3 * rc
    og_pts = -2 * og
    pm_pts = -2 * pens_missed
    ps_pts = 5 * pens_saved

    # Defensive contribution (capped at 2 pts total over the range)
    if pos == "DEF":
        dc_pts = 2 if dc_raw >= 10 else 0
    elif pos in ["MID", "FWD"]:
        dc_pts = 2 if dc_raw >= 12 else 0
    else:
        dc_pts = 0

    # Bonus is already FPL bonus
    bonus_pts = bonus

    # Sum up accounted points
    accounted = (
        minutes_points
        + goal_pts
        + assist_pts
        + cs_pts
        + save_pts
        + gc_pts
        + yc_pts
        + rc_pts
        + og_pts
        + pm_pts
        + ps_pts
        + dc_pts
        + bonus_pts
    )
    other_pts = total_points - accounted

    breakdown_rows = [
        ("Minutes", minutes_points),
        ("Goals", goal_pts),
        ("Assists", assist_pts),
        ("Clean Sheets", cs_pts),
        ("Bonus", bonus_pts),
        ("Saves", save_pts),
        ("Defensive Contributions", dc_pts),
        ("Goals Conceded", gc_pts),
        ("Yellow Cards", yc_pts),
        ("Red Cards", rc_pts),
        ("Own Goals", og_pts),
        ("Penalties Missed", pm_pts),
        ("Penalties Saved", ps_pts),
    ]

    # Only include "Other/Unaccounted" if non-zero
    if other_pts != 0:
        breakdown_rows.append(("Other / Unaccounted", other_pts))

    breakdown_df = pd.DataFrame(breakdown_rows, columns=["Category", "Total Points"])

    return {
        "has_data": True,
        "name": web_name,
        "position": pos,
        "history_df": df,
        "breakdown_df": breakdown_df,
        "total_points": total_points,
    }


# =====================================
# PLAYER DETAIL / COMPARISON SECTION
# =====================================
player_a_name = st.session_state.selected_player
player_b_name = st.session_state.selected_player2

if player_a_name != "None":
    # Build data for Player A
    a_data = build_player_breakdown(player_a_name)

    # Optional Player B
    b_data = None
    if player_b_name != "None" and player_b_name != player_a_name:
        b_data = build_player_breakdown(player_b_name)

    title = f"📌 Player Analysis — {player_a_name}"
    if b_data and b_data.get("has_data", False):
        title += f" vs {player_b_name}"

    st.title(title)

    # =========================
    # RADAR CHART (Comparison)
    # =========================
    if b_data and a_data.get("has_data", False) and b_data.get("has_data", False):
        categories = [
            "Goals",
            "Assists",
            "Clean Sheets",
            "Bonus",
            "Saves",
            "Defensive Contributions",
            "Minutes",
            "Total Points",
        ]

        def extract_for_radar(pdata):
            bd = pdata["breakdown_df"].set_index("Category")["Total Points"]
            vals = []
            for cat in categories:
                if cat == "Minutes":
                    # use Minutes points from row "Minutes"
                    vals.append(float(bd.get("Minutes", 0)))
                elif cat == "Total Points":
                    vals.append(float(pdata["total_points"]))
                else:
                    vals.append(float(bd.get(cat, 0)))
            return vals

        r1 = extract_for_radar(a_data)
        r2 = extract_for_radar(b_data)

        fig_radar = go.Figure()
        fig_radar.add_trace(
            go.Scatterpolar(
                r=r1,
                theta=categories,
                fill="toself",
                name=a_data["name"],
            )
        )
        fig_radar.add_trace(
            go.Scatterpolar(
                r=r2,
                theta=categories,
                fill="toself",
                name=b_data["name"],
            )
        )
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True)),
            showlegend=True,
            title="Player Comparison Radar (FPL Points by Category)",
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    # =========================
    # FPL POINTS CONTRIBUTION
    # =========================
    st.markdown("### 🧮 FPL Points Contribution")

    if b_data and a_data.get("has_data", False) and b_data.get("has_data", False):
        dfA = a_data["breakdown_df"].copy()
        dfB = b_data["breakdown_df"].copy()

        comp = dfA.merge(dfB, on="Category", suffixes=(" A", " B"))

        def winner_style(row):
            styles = []
            a = row["Total Points A"]
            b = row["Total Points B"]
            # Column order: Total Points A, Total Points B
            if a > b:
                styles = ["background-color:#c7f7c7", ""]
            elif b > a:
                styles = ["", "background-color:#c7f7c7"]
            else:
                styles = ["", ""]
            return styles

        styled_comp = comp.style.apply(
            lambda r: winner_style(r),
            axis=1,
            subset=["Total Points A", "Total Points B"],
        )

        st.dataframe(
            styled_comp,
            hide_index=True,
            use_container_width=True,
            height=min(700, (len(comp) + 2) * 40),
        )

    elif a_data.get("has_data", False):
        st.dataframe(
            a_data["breakdown_df"],
            hide_index=True,
            use_container_width=True,
            height=min(600, (len(a_data["breakdown_df"]) + 1) * 40),
        )
    else:
        st.info("No weekly data available for this player in the selected GW range.")

    # =========================
    # GW BREAKDOWN TABLE
    # =========================
    if a_data.get("has_data", False):
        df_hist = a_data["history_df"]

        st.markdown(
            f"### 📊 Points Breakdown by Gameweek "
            f"(GW {st.session_state.gw_slider[0]}–{st.session_state.gw_slider[1]})"
        )

        # Columns + renames based on position
        show_cols = [
            ("round", "Gameweek"),
            ("total_points", "Points"),
            ("goals_scored", "Goals"),
            ("assists", "Assists"),
            ("clean_sheets", "Clean Sheets"),
            ("goals_conceded", "Goals Conceded"),
            ("bonus", "Bonus"),
            ("minutes", "Minutes"),
            ("yellow_cards", "Yellow Cards"),
            ("red_cards", "Red Cards"),
        ]

        if a_data["position"] == "GK":
            show_cols.append(("saves", "Saves"))

        df_disp = df_hist[[c[0] for c in show_cols]].rename(
            columns={a: b for a, b in show_cols}
        )
        st.dataframe(df_disp, hide_index=True, use_container_width=True)


# =====================================
# MAIN PAGE TABLE
# =====================================
st.markdown("<div class='main-container'>", unsafe_allow_html=True)

st.title("🔥 FPL Analytics Dashboard")
st.write("Using cached local data for fast loading.")

st.subheader("📊 Player Value Table")
st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Player": st.column_config.TextColumn("Player"),
        "Team": st.column_config.TextColumn("Team"),
        "Position": st.column_config.TextColumn("Position"),
        "Points (GW Range)": st.column_config.NumberColumn("Points (GW Range)"),
        "Current Price": st.column_config.NumberColumn("Price (£m)"),
        "Points Per Million": st.column_config.NumberColumn("PPM"),
        "Selected By %": st.column_config.NumberColumn("Selected %"),
        "Template Value": st.column_config.NumberColumn("Template Value"),
        "Differential Value": st.column_config.NumberColumn("Differential Value"),
    },
)

st.markdown("</div>", unsafe_allow_html=True)

