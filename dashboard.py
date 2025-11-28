import streamlit as st
import pandas as pd
import json
import base64
import os
import plotly.graph_objects as go

# =========================================
# SESSION STATE DEFAULTS
# =========================================
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "main"  # "main", "single", "compare"

if "selected_player" not in st.session_state:
    st.session_state.selected_player = "None"

if "compare_players" not in st.session_state:
    st.session_state.compare_players = []

if "compare_dropdown" not in st.session_state:
    st.session_state.compare_dropdown = "None"

if "reset_flag" not in st.session_state:
    st.session_state.reset_flag = False


# =========================================
# BACKGROUND IMAGE
# =========================================
def set_background(image_file: str):
    if not os.path.exists(image_file):
        return
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

        /* Hide table index */
        .row_heading.level0 {{display:none}}
        .blank {{display:none}}
        </style>
        """,
        unsafe_allow_html=True,
    )


IMAGE_PATH = "bg1.png"  # ensure this is in repo root
set_background(IMAGE_PATH)

# =========================================
# LOCAL CACHE PATHS
# =========================================
CACHE_DIR = "cache"
PLAYERS_FILE = os.path.join(CACHE_DIR, "players.json")
WEEKLY_FILE = os.path.join(CACHE_DIR, "weekly.json")


# =========================================
# LOADERS
# =========================================
@st.cache_data
def load_players() -> pd.DataFrame:
    with open(PLAYERS_FILE, "r") as f:
        data = json.load(f)

    df = pd.DataFrame(data["elements"])
    teams = (
        pd.DataFrame(data["teams"])[["id", "name"]]
        .rename(columns={"id": "team", "name": "Team"})
    )
    df = df.merge(teams, on="team", how="left")

    # Position map
    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    df["Position"] = df["element_type"].map(pos_map)

    # Pricing
    df["Current Price"] = df["now_cost"] / 10.0

    # Points per million (season total)
    df["Points Per Million (Season)"] = df["total_points"] / df["Current Price"]

    # Selection %
    df["Selected By (Decimal)"] = (
        pd.to_numeric(df["selected_by_percent"], errors="coerce") / 100.0
    )
    df["Selected By %"] = df["Selected By (Decimal)"] * 100.0

    # Template & Differential (season-level, but we recalc per GW range later)
    df["Template Value (Season)"] = (
        df["Points Per Million (Season)"] * df["Selected By (Decimal)"]
    )
    df["Differential Value (Season)"] = (
        df["Points Per Million (Season)"] * (1 - df["Selected By (Decimal)"])
    )

    return df


@st.cache_data
def load_weekly() -> dict:
    with open(WEEKLY_FILE, "r") as f:
        return json.load(f)


players = load_players()
weekly = load_weekly()

# Combined weekly df for slider bounds
weekly_df = pd.concat(
    [pd.DataFrame(v) for v in weekly.values()],
    ignore_index=True,
)

min_gw = int(weekly_df["round"].min())
max_gw = int(weekly_df["round"].max())

# Map player -> position for comparison logic
POS_BY_NAME = dict(zip(players["web_name"], players["Position"]))


# =========================================
# RESET LOGIC
# =========================================
def trigger_reset():
    """Set the reset_flag; actual reset happens before widget creation."""
    st.session_state.reset_flag = True


def apply_reset():
    """Apply reset to all relevant filters + modes."""
    st.session_state.team_filter = "All Teams"
    st.session_state.position_filter = "All"
    st.session_state.gw_slider = (min_gw, max_gw)
    st.session_state.sort_column = "Points (GW Range)"
    st.session_state.sort_order = "Descending"
    st.session_state.selected_player = "None"
    st.session_state.compare_dropdown = "None"
    st.session_state.compare_players = []
    st.session_state.view_mode = "main"


# If a reset was requested in previous run, apply it now (before widgets)
if st.session_state.reset_flag:
    apply_reset()
    st.session_state.reset_flag = False


# =========================================
# SIDEBAR FILTERS & CONTROLS
# =========================================
st.sidebar.title("🔍 Filters")

team_filter = st.sidebar.selectbox(
    "Team",
    ["All Teams"] + sorted(players["Team"].unique()),
    key="team_filter",
)

position_filter = st.sidebar.selectbox(
    "Position",
    ["All", "GK", "DEF", "MID", "FWD"],
    key="position_filter",
)

gw_start, gw_end = st.sidebar.slider(
    "Gameweek Range",
    min_value=min_gw,
    max_value=max_gw,
    value=st.session_state.get("gw_slider", (min_gw, max_gw)),
    key="gw_slider",
)

sort_column = st.sidebar.selectbox(
    "Sort Table By",
    [
        "Points (GW Range)",
        "Current Price",
        "Points Per Million",
        "Selected By %",
        "Template Value",
        "Differential Value",
    ],
    key="sort_column",
)

sort_order = st.sidebar.radio(
    "Sort Order",
    ["Descending", "Ascending"],
    key="sort_order",
)

st.sidebar.markdown("---")
st.sidebar.subheader("👤 Player Analysis / Comparison")

primary_select = st.sidebar.selectbox(
    "Primary Player",
    ["None"] + sorted(players["web_name"].unique()),
    key="selected_player",
)

# Compare options restricted to same position as primary (Option A)
if primary_select != "None" and primary_select in POS_BY_NAME:
    primary_pos = POS_BY_NAME[primary_select]
    same_pos_names = (
        players[players["Position"] == primary_pos]["web_name"].unique().tolist()
    )
    same_pos_names = [n for n in same_pos_names if n != primary_select]
    compare_options = ["None"] + sorted(same_pos_names)
    compare_label = f"Second Player (same position: {primary_pos})"
else:
    compare_options = ["None"] + sorted(players["web_name"].unique())
    compare_label = "Second Player (optional)"

compare_select = st.sidebar.selectbox(
    compare_label,
    compare_options,
    key="compare_dropdown",
)

col_btn1, col_btn2 = st.sidebar.columns(2)

with col_btn1:
    if st.button("View Player"):
        if st.session_state.selected_player != "None":
            st.session_state.view_mode = "single"
            st.session_state.compare_players = [st.session_state.selected_player]

with col_btn2:
    if st.button("Compare Players"):
        chosen = []
        if st.session_state.selected_player != "None":
            chosen.append(st.session_state.selected_player)
        if st.session_state.compare_dropdown != "None":
            chosen.append(st.session_state.compare_dropdown)
        # Deduplicate, keep order
        chosen = list(dict.fromkeys(chosen))
        if len(chosen) >= 2:
            st.session_state.compare_players = chosen[:2]
            st.session_state.view_mode = "compare"

st.sidebar.markdown("---")
st.sidebar.button("🔄 Reset All Filters", on_click=trigger_reset)


# =========================================
# HELPER: GW RANGE POINTS
# =========================================
def get_points_for_range(player_id: int, gw1: int, gw2: int) -> int:
    history = weekly.get(str(player_id), [])
    if not history:
        return 0
    df = pd.DataFrame(history)
    df = df[(df["round"] >= gw1) & (df["round"] <= gw2)]
    return int(df["total_points"].sum())


# =========================================
# FILTER + TABLE BUILD
# =========================================
filtered = players.copy()

if team_filter != "All Teams":
    filtered = filtered[filtered["Team"] == team_filter]

if position_filter != "All":
    filtered = filtered[filtered["Position"] == position_filter]

filtered["Points (GW Range)"] = filtered.apply(
    lambda row: get_points_for_range(row["id"], gw_start, gw_end),
    axis=1,
)

# Core table for dashboard
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

# Recalculate GW-range-based metrics
table["Points Per Million"] = table["Points (GW Range)"] / table["Current Price"]

sel_decimal = table["Selected By %"] / 100.0
table["Template Value"] = table["Points Per Million"] * sel_decimal
table["Differential Value"] = table["Points Per Million"] * (1 - sel_decimal)

# Round numeric columns
round_cols = [
    "Current Price",
    "Points (GW Range)",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value",
]
table[round_cols] = table[round_cols].round(2)

# Sorting
ascending = sort_order == "Ascending"
table = table.sort_values(by=sort_column, ascending=ascending)


# =========================================
# CONTRIBUTION CALCULATION
# =========================================
def build_points_contribution(df_hist: pd.DataFrame, position: str) -> tuple[pd.DataFrame, float]:
    """
    df_hist: weekly history for a single player filtered to GW range.
    position: "GK", "DEF", "MID", or "FWD".
    Returns (DataFrame[Category, Points, % of Total], total_points).
    """
    if df_hist.empty:
        contrib = {
            "Minutes": 0,
            "Goals": 0,
            "Assists": 0,
            "Clean Sheets": 0,
            "Goals Conceded": 0,
            "Saves": 0,
            "Penalties": 0,
            "Cards": 0,
            "Own Goals": 0,
            "Bonus": 0,
            "Defensive Contribution": 0,
        }
        df = pd.DataFrame(
            {"Category": list(contrib.keys()), "Points": list(contrib.values())}
        )
        df["% of Total"] = 0.0
        return df, 0.0

    total_points = df_hist["total_points"].sum()

    mins = df_hist["minutes"].fillna(0)
    goals_scored = df_hist["goals_scored"].fillna(0)
    assists = df_hist["assists"].fillna(0)
    clean_sheets = df_hist["clean_sheets"].fillna(0)
    goals_conceded = df_hist["goals_conceded"].fillna(0)
    yc = df_hist["yellow_cards"].fillna(0)
    rc = df_hist["red_cards"].fillna(0)
    own_goals = df_hist["own_goals"].fillna(0)
    saves = df_hist["saves"].fillna(0)
    pen_saved = df_hist["penalties_saved"].fillna(0)
    pen_missed = df_hist["penalties_missed"].fillna(0)
    bonus = df_hist["bonus"].fillna(0)
    dc = df_hist.get("defensive_contribution", pd.Series(0, index=df_hist.index)).fillna(0)

    # Minutes points
    minutes_points = ((mins > 0) & (mins < 60)) * 1 + (mins >= 60) * 2

    # Goals
    goal_points_map = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
    goals_points = goals_scored * goal_points_map.get(position, 0)

    # Assists
    assist_points = assists * 3

    # Clean sheets
    cs_mask = (mins >= 60) & (clean_sheets > 0)
    if position in ["GK", "DEF"]:
        cs_points = cs_mask * 4
    elif position == "MID":
        cs_points = cs_mask * 1
    else:
        cs_points = cs_mask * 0

    # Goals conceded
    if position in ["GK", "DEF"]:
        gc_points = -((goals_conceded // 2))
    else:
        gc_points = 0 * goals_conceded

    # Saves & penalties
    save_points = (saves // 3) * 1
    pen_save_points = pen_saved * 5
    pen_miss_points = pen_missed * -2

    # Cards
    card_points = yc * -1 + rc * -3

    # Own goals
    og_points = own_goals * -2

    # Defensive contribution – cap at 2 points
    if position == "DEF":
        dc_points = ((dc // 10).clip(upper=1)) * 2
    elif position in ["MID", "FWD"]:
        dc_points = ((dc // 12).clip(upper=1)) * 2
    else:
        dc_points = 0 * dc

    contrib = {
        "Minutes": minutes_points.sum(),
        "Goals": goals_points.sum(),
        "Assists": assist_points.sum(),
        "Clean Sheets": cs_points.sum(),
        "Goals Conceded": gc_points.sum(),
        "Saves": save_points.sum(),
        "Penalties": (pen_save_points + pen_miss_points).sum(),
        "Cards": card_points.sum(),
        "Own Goals": og_points.sum(),
        "Bonus": bonus.sum(),
        "Defensive Contribution": dc_points.sum(),
    }

    df = pd.DataFrame(
        {"Category": list(contrib.keys()), "Points": list(contrib.values())}
    )
    if total_points > 0:
        df["% of Total"] = (df["Points"] / total_points * 100).round(1)
    else:
        df["% of Total"] = 0.0

    return df, float(total_points)


# =========================================
# RADAR CHART (USING RAW POINTS)
# =========================================
def build_radar(contrib_dfs: list[pd.DataFrame], names: list[str]):
    """
    Radar on positive contribution categories only:
    Minutes, Goals, Assists, Clean Sheets, Saves, Bonus, Defensive Contribution.
    Uses raw points values (not normalised).
    """
    categories = [
        "Minutes",
        "Goals",
        "Assists",
        "Clean Sheets",
        "Saves",
        "Bonus",
        "Defensive Contribution",
    ]

    fig = go.Figure()

    for name, df_c in zip(names, contrib_dfs):
        d = df_c.set_index("Category")
        values = [float(d.loc[c, "Points"]) if c in d.index else 0.0 for c in categories]
        # Close the radar loop
        values += values[:1]
        theta = categories + [categories[0]]

        fig.add_trace(
            go.Scatterpolar(
                r=values,
                theta=theta,
                name=name,
                fill="toself",
            )
        )

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True)),
        showlegend=True,
        margin=dict(l=40, r=40, t=40, b=40),
    )
    return fig


# =========================================
# OVERLAY (SINGLE & COMPARE)
# =========================================
def show_overlay(player_names: list[str], gw1: int, gw2: int):
    st.markdown(
        """
        <div style="background-color: rgba(0,0,0,0.05); padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        """,
        unsafe_allow_html=True,
    )

    col_back, _ = st.columns([1, 3])
    with col_back:
        if st.button("⬅ Back to main dashboard & reset filters"):
            trigger_reset()
            st.rerun()

    # Collect per-player contributions for radar / comparison
    contrib_dfs = []
    totals = []
    meta_rows = []

    for name in player_names:
        p_row = players[players["web_name"] == name].iloc[0]
        pid = int(p_row["id"])
        pos = p_row["Position"]
        team = p_row["Team"]
        price = p_row["Current Price"]
        selected_pct = p_row["Selected By %"].round(2)

        history = weekly.get(str(pid), [])
        if not history:
            st.info(f"No weekly data available for **{name}**.")
            continue

        df_hist = pd.DataFrame(history)
        df_hist = df_hist[(df_hist["round"] >= gw1) & (df_hist["round"] <= gw2)]

        contrib_df, total_pts = build_points_contribution(df_hist, pos)
        contrib_dfs.append(contrib_df)
        totals.append(total_pts)
        meta_rows.append(
            {
                "Player": name,
                "Team": team,
                "Position": pos,
                "Price (£m)": price,
                "Selected %": selected_pct,
                f"Points (GW {gw1}-{gw2})": int(total_pts),
            }
        )

    if not contrib_dfs:
        st.info("No contribution data found for the selected players in this range.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Meta summary table
    st.markdown("### 🔍 GW-Range Summary")
    meta_df = pd.DataFrame(meta_rows)
    st.dataframe(meta_df, width="stretch", hide_index=True)

    # FPL Points Contribution
    st.markdown("### 📊 FPL Points Contribution")

    if len(player_names) == 1:
        # Single-player table: Category / Points / % of Total
        df_single = contrib_dfs[0].copy()
        df_single["Points"] = df_single["Points"].round(0).astype(int)
        st.dataframe(
            df_single,
            width="stretch",
            hide_index=True,
        )

    else:
        # Comparison table:
        # - Categories down left
        # - One column per player
        # - Each cell: "<points> (<% of total>%)"
        # - Winner per row gets a ⭐ prefix
        cats = contrib_dfs[0]["Category"].tolist()
        rows = []

        for cat in cats:
            row = {"Category": cat}
            # collect per-player numeric values to find winner
            pts_per_player = {}
            pct_per_player = {}

            for name, df_c in zip(player_names, contrib_dfs):
                d = df_c.set_index("Category")
                pts = float(d.loc[cat, "Points"]) if cat in d.index else 0.0
                pct = float(d.loc[cat, "% of Total"]) if cat in d.index else 0.0
                pts_per_player[name] = pts
                pct_per_player[name] = pct

            max_pts = max(pts_per_player.values()) if pts_per_player else 0.0

            for name in player_names:
                pts = pts_per_player.get(name, 0.0)
                pct = pct_per_player.get(name, 0.0)
                display_val = f"{int(round(pts, 0))} ({pct:.1f}%)"
                # Add star for winner(s) if max_pts > 0
                if max_pts > 0 and abs(pts - max_pts) < 1e-9:
                    display_val = f"⭐ {display_val}"
                row[name] = display_val

            rows.append(row)

        comp_df = pd.DataFrame(rows)[["Category"] + player_names]
        st.dataframe(comp_df, width="stretch", hide_index=True)

    # Radar chart (points values)
    st.markdown("### 🕸 Radar View (Positive Contributions)")
    radar_fig = build_radar(contrib_dfs, player_names)
    st.plotly_chart(radar_fig, width="stretch")

    # Per-player GW breakdown tables
    for name in player_names:
        p_row = players[players["web_name"] == name].iloc[0]
        pid = int(p_row["id"])
        pos = p_row["Position"]

        history = weekly.get(str(pid), [])
        if not history:
            continue

        df_hist = pd.DataFrame(history)
        df_hist = df_hist[(df_hist["round"] >= gw1) & (df_hist["round"] <= gw2)]

        if df_hist.empty:
            continue

        st.markdown(f"### 📅 Points Breakdown by Gameweek — {name} (GW {gw1}-{gw2})")

        cols = [
            "round",
            "total_points",
            "goals_scored",
            "assists",
            "clean_sheets",
            "goals_conceded",
            "bonus",
            "minutes",
            "yellow_cards",
            "red_cards",
        ]

        # Saves only meaningful for GK
        if pos == "GK":
            cols.append("saves")

        df_view = df_hist[cols].copy().sort_values("round")

        rename_map = {
            "round": "Gameweek",
            "total_points": "Points",
            "goals_scored": "Goals",
            "assists": "Assists",
            "clean_sheets": "Clean Sheets",
            "goals_conceded": "Goals Conceded",
            "bonus": "Bonus",
            "minutes": "Minutes",
            "yellow_cards": "Yellow Cards",
            "red_cards": "Red Cards",
            "saves": "Saves",
        }
        df_view = df_view.rename(columns=rename_map)

        # Only show Clean Sheets / Goals Conceded if GK/DEF/MID (per your spec)
        if pos not in ["GK", "DEF", "MID"]:
            df_view = df_view.drop(columns=["Clean Sheets", "Goals Conceded"], errors="ignore")

        st.dataframe(df_view, width="stretch", hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================
# PAGE CONTENT
# =========================================
st.markdown("<div class='main-container'>", unsafe_allow_html=True)

st.title("🔥 FPL Simple Analytics")
st.write("Using cached FPL data with GW-range value metrics and player analysis.")

# Overlay for view / comparison
if st.session_state.view_mode == "single" and st.session_state.selected_player != "None":
    show_overlay([st.session_state.selected_player], gw_start, gw_end)

elif (
    st.session_state.view_mode == "compare"
    and len(st.session_state.compare_players) >= 2
):
    show_overlay(st.session_state.compare_players[:2], gw_start, gw_end)

# Only show main table when in main mode
if st.session_state.view_mode == "main":
    st.subheader("📊 Player Value Table")

    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "Player": st.column_config.TextColumn(
                "Player",
                help="Player’s short name (web_name from FPL API)",
            ),
            "Team": st.column_config.TextColumn(
                "Team",
                help="Premier League team",
            ),
            "Position": st.column_config.TextColumn(
                "Pos",
                help="GK, DEF, MID, or FWD",
            ),
            "Points (GW Range)": st.column_config.NumberColumn(
                f"Points (GW {gw_start}-{gw_end})",
                help="Total FPL points between selected gameweeks",
            ),
            "Current Price": st.column_config.NumberColumn(
                "Price (£m)",
                help="Current FPL price (now_cost / 10)",
                format="£%.1f",
            ),
            "Points Per Million": st.column_config.NumberColumn(
                "PPM",
                help="Points (GW Range) divided by current price",
                format="%.2f",
            ),
            "Selected By %": st.column_config.NumberColumn(
                "Selected %",
                help="Percentage of FPL managers who own this player",
                format="%.2f",
            ),
            "Template Value": st.column_config.NumberColumn(
                "Template Value",
                help="PPM × Selected %. Higher = template pick",
                format="%.2f",
            ),
            "Differential Value": st.column_config.NumberColumn(
                "Differential Value",
                help="PPM × (1 – Selected %). Higher = differential pick",
                format="%.2f",
            ),
        },
    )

st.markdown("</div>", unsafe_allow_html=True)
