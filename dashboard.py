import streamlit as st
import pandas as pd
import json
import base64
import os
import plotly.express as px

# -----------------------------------------
# BACKGROUND IMAGE
# -----------------------------------------
def set_background(image_file):
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
        unsafe_allow_html=True
    )

IMAGE_PATH = "bg1.png"   # Ensure bg1.png exists in repo root
set_background(IMAGE_PATH)


# -----------------------------------------
# LOAD LOCAL CACHE FILES
# -----------------------------------------
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

    # Position map
    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    df["Position"] = df["element_type"].map(pos_map)

    # Pricing
    df["Current Price"] = df["now_cost"] / 10

    # Season-long PPM (we override with GW-range later)
    df["Points Per Million"] = df["total_points"] / df["Current Price"]

    # Selection %
    df["Selected By (Decimal)"] = pd.to_numeric(
        df["selected_by_percent"], errors="coerce"
    ) / 100
    df["Selected By %"] = df["Selected By (Decimal)"] * 100

    # Template & differential (season-based baseline)
    df["Template Value"] = df["Points Per Million"] * df["Selected By (Decimal)"]
    df["Differential Value"] = df["Points Per Million"] * (
        1 - df["Selected By (Decimal)"]
    )

    return df


@st.cache_data
def load_weekly():
    with open(WEEKLY_FILE, "r") as f:
        return json.load(f)


players = load_players()
weekly = load_weekly()

# -----------------------------------------
# BUILD WEEKLY DF FOR SLIDER LIMITS
# -----------------------------------------
weekly_df = pd.concat(
    [pd.DataFrame(v) for v in weekly.values()],
    ignore_index=True
)

min_gw = int(weekly_df["round"].min())
max_gw = int(weekly_df["round"].max())


# -----------------------------------------
# SIDEBAR FILTERS + RESET LOGIC
# -----------------------------------------
st.sidebar.title("🔍 Filters")

# Reset flag in session state
if "reset_triggered" not in st.session_state:
    st.session_state.reset_triggered = False

# 🔄 Reset button FIRST, before widgets
if st.sidebar.button("🔄 Reset All Filters"):
    st.session_state.reset_triggered = True
    st.rerun()

# If reset was triggered, reset all filter-related state and rerun
if st.session_state.reset_triggered:
    st.session_state.team_filter = "All Teams"
    st.session_state.position_filter = "All"
    st.session_state.gw_slider = (min_gw, max_gw)
    st.session_state.sort_column = "Points (GW Range)"
    st.session_state.sort_order = "Descending"
    st.session_state.selected_player = "None"
    st.session_state.reset_triggered = False
    st.rerun()

# Now safely create all widgets
team_filter = st.sidebar.selectbox(
    "Team",
    ["All Teams"] + sorted(players["Team"].unique()),
    key="team_filter"
)

position_filter = st.sidebar.selectbox(
    "Position",
    ["All", "GK", "DEF", "MID", "FWD"],
    key="position_filter"
)

gw_start, gw_end = st.sidebar.slider(
    "Gameweek Range",
    min_value=min_gw,
    max_value=max_gw,
    value=(min_gw, max_gw),
    key="gw_slider"
)

sort_column = st.sidebar.selectbox(
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

sort_order = st.sidebar.radio(
    "Sort Order",
    ["Descending", "Ascending"],
    key="sort_order"
)

selected_player = st.sidebar.selectbox(
    "View Player Details",
    ["None"] + sorted(players["web_name"].unique()),
    key="selected_player"
)


# -----------------------------------------
# FILTER BASE TABLE
# -----------------------------------------
filtered = players.copy()

if team_filter != "All Teams":
    filtered = filtered[filtered["Team"] == team_filter]

if position_filter != "All":
    filtered = filtered[filtered["Position"] == position_filter]


# -----------------------------------------
# GAMEWEEK-RANGE POINT CALCULATION
# -----------------------------------------
def get_points_for_range(player_id, gw1, gw2):
    history = weekly.get(str(player_id), [])
    if not history:
        return 0
    df = pd.DataFrame(history)
    df = df[(df["round"] >= gw1) & (df["round"] <= gw2)]
    return df["total_points"].sum()


filtered["Points (GW Range)"] = filtered.apply(
    lambda row: get_points_for_range(row["id"], gw_start, gw_end),
    axis=1
)


# -----------------------------------------
# FINAL TABLE
# -----------------------------------------
table = filtered[[
    "web_name",
    "Team",
    "Position",
    "Points (GW Range)",
    "Current Price",
    "Selected By %"
]].rename(columns={"web_name": "Player"})

# Recalculate dynamic metrics based on GW-range points
table["Points Per Million"] = table["Points (GW Range)"] / table["Current Price"]

sel_decimal = table["Selected By %"] / 100
table["Template Value"] = table["Points Per Million"] * sel_decimal
table["Differential Value"] = table["Points Per Million"] * (1 - sel_decimal)

# Round numbers
round_cols = [
    "Current Price",
    "Points (GW Range)",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value"
]

table[round_cols] = table[round_cols].round(2)

# Sorting
ascending = (sort_order == "Ascending")
table = table.sort_values(by=sort_column, ascending=ascending)


# -----------------------------------------
# PLAYER DETAIL PANEL (GW-RANGE BREAKDOWN)
# -----------------------------------------
if selected_player != "None":

    player_name = selected_player
    st.subheader(f"📌 Detailed FPL Breakdown — {player_name} (GW {gw_start}–{gw_end})")

    # Get player row & ID
    player_row = players[players["web_name"] == player_name].iloc[0]
    pid = int(player_row["id"])
    position = player_row["Position"]

    history = weekly.get(str(pid), [])

    if history:
        df_hist = pd.DataFrame(history)

        # Restrict to GW range
        df_range = df_hist[
            (df_hist["round"] >= gw_start) & (df_hist["round"] <= gw_end)
        ].copy()

        if df_range.empty:
            st.info(f"No games for {player_name} between GW {gw_start} and {gw_end}.")
        else:
            # ---- GW Range Summary ----
            total_points_range = df_range["total_points"].sum()
            st.markdown("### 🔍 GW-Range Summary")
            st.write(
                pd.DataFrame(
                    {
                        "Team": [player_row["Team"]],
                        "Position": [position],
                        "Current Price": [round(player_row["Current Price"], 2)],
                        "Selected By %": [round(player_row["Selected By %"], 2)],
                        f"Total Points (GW {gw_start}-{gw_end})": [int(total_points_range)],
                    }
                )
            )

            # ---- Points Breakdown by Gameweek (GW range only) ----
            st.markdown(f"### 📊 Points Breakdown by Gameweek (GW {gw_start}–{gw_end})")
            st.dataframe(
                df_range[[
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
                    "saves",
                    "expected_goals",
                    "expected_assists",
                    "expected_goal_involvements",
                ]].sort_values("round"),
                use_container_width=True,
            )

            # ---- Aggregate Stats for GW Range ----
            goals = df_range["goals_scored"].sum()
            assists = df_range["assists"].sum()
            clean_sheets = df_range["clean_sheets"].sum()
            goals_conceded = df_range["goals_conceded"].sum()
            own_goals = df_range["own_goals"].sum()
            pens_saved = df_range["penalties_saved"].sum()
            pens_missed = df_range["penalties_missed"].sum()
            yellow_cards = df_range["yellow_cards"].sum()
            red_cards = df_range["red_cards"].sum()
            saves = df_range["saves"].sum()
            bonus = df_range["bonus"].sum()
            minutes_series = df_range["minutes"]

            apps_60 = ((minutes_series >= 60)).sum()
            apps_sub = ((minutes_series > 0) & (minutes_series < 60)).sum()

            # ---- FPL Scoring Rules ----
            if position in ["GK", "DEF"]:
                goal_points_per = 6
                cs_points_per = 4
                gc_points = -(goals_conceded // 2)  # -1 per 2 conceded
            elif position == "MID":
                goal_points_per = 5
                cs_points_per = 1
                gc_points = 0
            else:  # FWD
                goal_points_per = 4
                cs_points_per = 0
                gc_points = 0

            assists_points_per = 3
            minutes_points = apps_60 * 2 + apps_sub * 1
            goals_points = goals * goal_points_per
            assists_points = assists * assists_points_per
            cs_points = clean_sheets * cs_points_per

            if position == "GK":
                saves_points = (saves // 3) * 1
            else:
                saves_points = 0

            yc_points = -1 * yellow_cards
            rc_points = -3 * red_cards
            og_points = -2 * own_goals
            ps_points = 5 * pens_saved
            pm_points = -2 * pens_missed
            bonus_points = bonus

            # Build breakdown table
            rows = []

            rows.append({
                "Category": "Goals",
                "Count": int(goals),
                "Points per Event": goal_points_per,
                "Total Points": int(goals_points),
            })
            rows.append({
                "Category": "Assists",
                "Count": int(assists),
                "Points per Event": assists_points_per,
                "Total Points": int(assists_points),
            })
            rows.append({
                "Category": "Clean Sheets",
                "Count": int(clean_sheets),
                "Points per Event": cs_points_per,
                "Total Points": int(cs_points),
            })
            rows.append({
                "Category": "Minutes (60+)",
                "Count": int(apps_60),
                "Points per Event": 2,
                "Total Points": int(apps_60 * 2),
            })
            rows.append({
                "Category": "Minutes (<60)",
                "Count": int(apps_sub),
                "Points per Event": 1,
                "Total Points": int(apps_sub * 1),
            })
            if position == "GK":
                rows.append({
                    "Category": "Saves",
                    "Count": int(saves),
                    "Points per Event": "1 per 3",
                    "Total Points": int(saves_points),
                })
            if position in ["GK", "DEF"]:
                rows.append({
                    "Category": "Goals Conceded",
                    "Count": int(goals_conceded),
                    "Points per Event": "-1 per 2",
                    "Total Points": int(gc_points),
                })
            rows.append({
                "Category": "Bonus",
                "Count": int(bonus),
                "Points per Event": 1,
                "Total Points": int(bonus_points),
            })
            rows.append({
                "Category": "Yellow Cards",
                "Count": int(yellow_cards),
                "Points per Event": -1,
                "Total Points": int(yc_points),
            })
            rows.append({
                "Category": "Red Cards",
                "Count": int(red_cards),
                "Points per Event": -3,
                "Total Points": int(rc_points),
            })
            rows.append({
                "Category": "Own Goals",
                "Count": int(own_goals),
                "Points per Event": -2,
                "Total Points": int(og_points),
            })
            rows.append({
                "Category": "Penalties Saved",
                "Count": int(pens_saved),
                "Points per Event": 5,
                "Total Points": int(ps_points),
            })
            rows.append({
                "Category": "Penalties Missed",
                "Count": int(pens_missed),
                "Points per Event": -2,
                "Total Points": int(pm_points),
            })

            breakdown_df = pd.DataFrame(rows)

            # Only keep rows that actually contributed something
            breakdown_df = breakdown_df[breakdown_df["Count"] != 0].reset_index(drop=True)

            calc_total = breakdown_df["Total Points"].sum()

            st.markdown(f"### 🧮 FPL Points Contribution (GW {gw_start}–{gw_end})")
            st.write(f"**Total from breakdown:** {int(calc_total)} points")
            st.write(f"**Total from API (sum of total_points):** {int(total_points_range)} points")

            st.dataframe(
                breakdown_df,
                use_container_width=True,
            )

            # ---- Bar Chart: Points by Category ----
            st.markdown("### 📈 Points Contribution by Category")
            if not breakdown_df.empty:
                fig_bar = px.bar(
                    breakdown_df,
                    x="Category",
                    y="Total Points",
                    title=f"Points Contribution (GW {gw_start}–{gw_end}) — {player_name}",
                )
                st.plotly_chart(fig_bar, use_container_width=True)

            # ---- Line Chart: Points per GW (range only) ----
            st.markdown("### 📉 Points per Gameweek (GW Range)")
            fig_line = px.line(
                df_range.sort_values("round"),
                x="round",
                y="total_points",
                markers=True,
                title=f"Points per GW — {player_name} (GW {gw_start}–{gw_end})",
            )
            st.plotly_chart(fig_line, use_container_width=True)

    else:
        st.info("No weekly data available for this player.")


# -----------------------------------------
# PAGE CONTENT
# -----------------------------------------
st.markdown("<div class='main-container'>", unsafe_allow_html=True)

st.title("🔥 FPL Analytics Dashboard")
st.write("Using cached local data for instant loading.")

st.subheader("📊 Player Value Table")
st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
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
    }
)

st.markdown("</div>", unsafe_allow_html=True)
