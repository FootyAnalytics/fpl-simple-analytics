import streamlit as st
import pandas as pd
import json
import base64
import os
import plotly.graph_objects as go

# -----------------------------------------
# Session State Defaults
# -----------------------------------------
if "selected_player" not in st.session_state:
    st.session_state.selected_player = "None"
if "selected_player2" not in st.session_state:
    st.session_state.selected_player2 = "None"


# -----------------------------------------
# BACKGROUND IMAGE
# -----------------------------------------
def set_background(image_file):
    if not os.path.exists(image_file):
        return  # skip on streamlit cloud

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


# -----------------------------------------
# LOAD CACHE FILES
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

    df = df.merge(teams, on="team")

    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    df["Position"] = df["element_type"].map(pos_map)

    df["Current Price"] = df["now_cost"] / 10
    df["Selected By (Decimal)"] = pd.to_numeric(df["selected_by_percent"], errors="coerce") / 100
    df["Selected By %"] = df["Selected By (Decimal)"] * 100

    return df


@st.cache_data
def load_weekly():
    with open(WEEKLY_FILE, "r") as f:
        return json.load(f)


players = load_players()
weekly = load_weekly()

# Weekly DF to find GW limits
weekly_df = pd.concat([pd.DataFrame(v) for v in weekly.values()], ignore_index=True)
min_gw = int(weekly_df["round"].min())
max_gw = int(weekly_df["round"].max())


# -----------------------------------------
# HELPER — Points in GW Range
# -----------------------------------------
def get_points_for_range(player_id, gw1, gw2):
    history = weekly.get(str(player_id), [])
    if not history:
        return 0
    df = pd.DataFrame(history)
    df = df[(df["round"] >= gw1) & (df["round"] <= gw2)]
    return df["total_points"].sum()


# -----------------------------------------
# SIDEBAR FILTERS (FORM)
# -----------------------------------------
with st.sidebar.form("filters_form"):
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
        min_gw,
        max_gw,
        (min_gw, max_gw),
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
            "Differential Value",
        ],
        key="sort_column"
    )

    sort_order = st.radio(
        "Sort Order",
        ["Descending", "Ascending"],
        key="sort_order"
    )

    reset_clicked = st.form_submit_button("🔄 Reset All Filters")

if reset_clicked:
    st.session_state.clear()
    st.rerun()

# Player selection (outside form)
st.sidebar.header("👤 Player Analysis")
st.session_state.selected_player = st.sidebar.selectbox(
    "Player A",
    ["None"] + sorted(players["web_name"].unique()),
    key="playerA"
)

st.session_state.selected_player2 = st.sidebar.selectbox(
    "Player B (Compare)",
    ["None"] + sorted(players["web_name"].unique()),
    key="playerB"
)


# -----------------------------------------
# FILTER MAIN TABLE
# -----------------------------------------
filtered = players.copy()

if st.session_state.team_filter != "All Teams":
    filtered = filtered[filtered["Team"] == st.session_state.team_filter]

if st.session_state.position_filter != "All":
    filtered = filtered[filtered["Position"] == st.session_state.position_filter]

filtered["Points (GW Range)"] = filtered.apply(
    lambda r: get_points_for_range(
        r["id"],
        st.session_state.gw_slider[0],
        st.session_state.gw_slider[1]
    ),
    axis=1
)

# Build full table
table = filtered[[
    "web_name",
    "Team",
    "Position",
    "Points (GW Range)",
    "Current Price",
    "Selected By %",
]].rename(columns={"web_name": "Player"})

table["Points Per Million"] = table["Points (GW Range)"] / table["Current Price"]
sel_dec = table["Selected By %"] / 100
table["Template Value"] = table["Points Per Million"] * sel_dec
table["Differential Value"] = table["Points Per Million"] * (1 - sel_dec)

round_cols = [
    "Current Price",
    "Points (GW Range)",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value"
]
table[round_cols] = table[round_cols].round(2)

ascending = st.session_state.sort_order == "Ascending"
table = table.sort_values(by=st.session_state.sort_column, ascending=ascending)


# -----------------------------------------
# PLAYER BREAKDOWN FUNCTION
# -----------------------------------------
def build_player_breakdown(web_name):
    row = players[players["web_name"] == web_name]
    if row.empty:
        return {"has_data": False}

    pid = int(row["id"].iloc[0])
    pos = row["Position"].iloc[0]

    history = weekly.get(str(pid), [])
    if not history:
        return {"has_data": False}

    df = pd.DataFrame(history)
    df = df[
        (df["round"] >= st.session_state.gw_slider[0]) &
        (df["round"] <= st.session_state.gw_slider[1])
    ]

    if df.empty:
        return {"has_data": False}

    # Raw stats
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
    pm = df["penalties_missed"].sum()
    ps = df["penalties_saved"].sum()
    dc_raw = df.get("defensive_contribution", pd.Series([0]*len(df))).sum()
    total_pts = df["total_points"].sum()

    # Minutes points
    minutes_pts = sum(2 if m >= 60 else 1 if m > 0 else 0 for m in df["minutes"])

    # Goal points
    goal_pts_map = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
    goal_pts = goals * goal_pts_map[pos]

    assist_pts = assists * 3

    # Clean sheet
    if pos in ["GK", "DEF"]:
        cs_pts = cs * 4
    elif pos == "MID":
        cs_pts = cs * 1
    else:
        cs_pts = 0

    # Saves
    save_pts = (saves // 3) * 1 if pos == "GK" else 0

    # Goals conceded
    gc_pts = -(gc // 2) if pos in ["GK", "DEF"] else 0

    # Cards
    yc_pts = -yc
    rc_pts = -3 * rc

    # Own goals
    og_pts = -2 * og

    # Penalties
    pm_pts = -2 * pm
    ps_pts = 5 * ps

    # Defensive contribution (capped)
    if pos == "DEF":
        dc_pts = 2 if dc_raw >= 10 else 0
    elif pos in ["MID", "FWD"]:
        dc_pts = 2 if dc_raw >= 12 else 0
    else:
        dc_pts = 0

    accounted = (
        minutes_pts + goal_pts + assist_pts + cs_pts + save_pts +
        gc_pts + yc_pts + rc_pts + og_pts + pm_pts + ps_pts +
        dc_pts + bonus
    )
    other = total_pts - accounted

    rows = [
        ("Minutes", minutes_pts),
        ("Goals", goal_pts),
        ("Assists", assist_pts),
        ("Clean Sheets", cs_pts),
        ("Bonus", bonus),
        ("Saves", save_pts),
        ("Defensive Contributions", dc_pts),
        ("Goals Conceded", gc_pts),
        ("Yellow Cards", yc_pts),
        ("Red Cards", rc_pts),
        ("Own Goals", og_pts),
        ("Penalties Missed", pm_pts),
        ("Penalties Saved", ps_pts),
    ]

    if other != 0:
        rows.append(("Other / Unaccounted", other))

    breakdown_df = pd.DataFrame(rows, columns=["Category", "Total Points"])

    return {
        "has_data": True,
        "name": web_name,
        "position": pos,
        "history_df": df,
        "breakdown_df": breakdown_df,
        "total_points": total_pts,
    }


# -----------------------------------------
# PREMIUM MODAL POPUP RESTORED HERE
# -----------------------------------------

playerA = st.session_state.selected_player
playerB = st.session_state.selected_player2

if playerA != "None":
    with st.modal(f"📌 Player Analysis — {playerA}"):
        A = build_player_breakdown(playerA)
        B = None
        if playerB != "None" and playerB != playerA:
            B = build_player_breakdown(playerB)

        # -------------------------------------
        # Radar Chart
        # -------------------------------------
        if B and A["has_data"] and B["has_data"]:
            categories = [
                "Goals", "Assists", "Clean Sheets",
                "Bonus", "Saves", "Defensive Contributions",
                "Minutes", "Total Points"
            ]

            def radar_vals(P):
                b = P["breakdown_df"].set_index("Category")["Total Points"]
                vals = []
                for c in categories:
                    if c == "Total Points":
                        vals.append(P["total_points"])
                    elif c == "Minutes":
                        vals.append(b.get("Minutes", 0))
                    else:
                        vals.append(b.get(c, 0))
                return vals

            rA = radar_vals(A)
            rB = radar_vals(B)

            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(r=rA, theta=categories, fill="toself", name=playerA))
            fig.add_trace(go.Scatterpolar(r=rB, theta=categories, fill="toself", name=playerB))

            fig.update_layout(
                title="FPL Points Radar Chart",
                showlegend=True,
                polar=dict(radialaxis=dict(visible=True)),
            )

            st.plotly_chart(fig, use_container_width=True)

        # -------------------------------------
        # Contribution Table (with Winner Highlight)
        # -------------------------------------
        st.subheader("🧮 FPL Points Contribution")
        if B and A["has_data"] and B["has_data"]:
            dfA = A["breakdown_df"].copy()
            dfB = B["breakdown_df"].copy()

            merged = dfA.merge(dfB, on="Category", suffixes=(" A", " B"))

            def highlight(row):
                a = row["Total Points A"]
                b = row["Total Points B"]
                if a > b:
                    return ["background-color:#c7f7c7", ""]
                elif b > a:
                    return ["", "background-color:#c7f7c7"]
                else:
                    return ["", ""]

            styled = merged.style.apply(
                lambda r: highlight(r),
                axis=1,
                subset=["Total Points A", "Total Points B"]
            )

            st.dataframe(styled, hide_index=True, width="stretch")
        else:
            st.dataframe(A["breakdown_df"], hide_index=True, width="stretch")

        # -------------------------------------
        # Gameweek Breakdown Table
        # -------------------------------------
        st.subheader(f"📊 Gameweek Breakdown (GW {st.session_state.gw_slider[0]}–{st.session_state.gw_slider[1]})")

        dfh = A["history_df"]

        cols = [
            ("round", "Gameweek"),
            ("total_points", "Points"),
            ("goals_scored", "Goals"),
            ("assists", "Assists"),
            ("clean_sheets", "Clean Sheets"),
            ("goals_conceded", "Goals Conceded"),
            ("bonus", "Bonus"),
            ("minutes", "Minutes"),
            ("yellow_cards", "Yellow Cards"),
            ("red_cards", "Red Cards")
        ]
        if A["position"] == "GK":
            cols.append(("saves", "Saves"))

        df_show = dfh[[c[0] for c in cols]].rename(columns={a: b for a, b in cols})
        st.dataframe(df_show, hide_index=True, width="stretch")


# -----------------------------------------
# MAIN TABLE
# -----------------------------------------
st.markdown("<div class='main-container'>", unsafe_allow_html=True)
st.title("🔥 FPL Analytics Dashboard")

st.subheader("📊 Player Value Table")
st.dataframe(
    table,
    hide_index=True,
    width="stretch"
)

st.markdown("</div>", unsafe_allow_html=True)
