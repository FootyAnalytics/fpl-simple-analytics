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

        /* OVERLAY EXIT BUTTON */
        .exit-button-container {{
            position: fixed;
            top: 20px;
            right: 40px;
            z-index: 9999;
        }}
        .exit-btn {{
            background-color: #d9534f;
            color: white;
            padding: 10px 18px;
            border-radius: 8px;
            font-size: 16px;
            border: none;
            cursor: pointer;
            transition: 0.25s all ease-in-out;
        }}
        .exit-btn:hover {{
            background-color: #c9302c;
            transform: scale(1.05);
        }}

        /* Fade animation */
        .fadeout {{
            animation: fadeOut 0.4s ease forwards;
        }}
        @keyframes fadeOut {{
            from {{opacity: 1;}}
            to {{opacity: 0;}}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


IMAGE_PATH = "bg1.png"
set_background(IMAGE_PATH)

# Inject ESC key listener
st.markdown(
    """
<script>
document.addEventListener('keydown', function(e) {
    if (e.key === "Escape") {
        const btn = window.parent.document.querySelector('#exit_overlay_button');
        if (btn) btn.click();
    }
});
</script>
""",
    unsafe_allow_html=True,
)

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
    df = df.merge(teams, on="team", how="left")

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

weekly_df = pd.concat([pd.DataFrame(v) for v in weekly.values()], ignore_index=True)
min_gw = int(weekly_df["round"].min())
max_gw = int(weekly_df["round"].max())


def get_points_for_range(player_id: int, gw1: int, gw2: int) -> int:
    history = weekly.get(str(player_id), [])
    if not history:
        return 0
    df = pd.DataFrame(history)
    df = df[(df["round"] >= gw1) & (df["round"] <= gw2)]
    return int(df["total_points"].sum())


# -----------------------------------------
# SIDEBAR FILTERS
# -----------------------------------------
st.sidebar.title("🔍 Filters & Player View")

# Reset button
if st.sidebar.button("🔄 Reset All Filters"):
    st.session_state.clear()
    st.session_state.selected_player = "None"
    st.session_state.selected_player2 = "None"
    st.rerun()

team_filter = st.sidebar.selectbox(
    "Team",
    ["All Teams"] + sorted(players["Team"].unique()),
)

position_filter = st.sidebar.selectbox(
    "Position",
    ["All", "GK", "DEF", "MID", "FWD"],
)

gw_start, gw_end = st.sidebar.slider(
    "Gameweek Range",
    min_value=min_gw,
    max_value=max_gw,
    value=(min_gw, max_gw),
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
)

sort_order = st.sidebar.radio(
    "Sort Order",
    ["Descending", "Ascending"],
)

# Player selection
st.sidebar.markdown("---")
st.sidebar.subheader("👤 Player Analysis")
playerA = st.sidebar.selectbox(
    "Player A",
    ["None"] + sorted(players["web_name"].unique()),
)
playerB = st.sidebar.selectbox(
    "Player B (Compare)",
    ["None"] + sorted(players["web_name"].unique()),
)

st.session_state.selected_player = playerA
st.session_state.selected_player2 = playerB


# -----------------------------------------
# MAIN TABLE FILTERING
# -----------------------------------------
filtered = players.copy()

if team_filter != "All Teams":
    filtered = filtered[filtered["Team"] == team_filter]

if position_filter != "All":
    filtered = filtered[filtered["Position"] == position_filter]

filtered["Points (GW Range)"] = filtered.apply(
    lambda r: get_points_for_range(r["id"], gw_start, gw_end),
    axis=1,
)

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

table["Points Per Million"] = table["Points (GW Range)"] / table["Current Price"]
sel_decimal = table["Selected By %"] / 100
table["Template Value"] = table["Points Per Million"] * sel_decimal
table["Differential Value"] = table["Points Per Million"] * (1 - sel_decimal)

round_cols = [
    "Current Price",
    "Points (GW Range)",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value",
]
table[round_cols] = table[round_cols].round(2)

ascending = sort_order == "Ascending"
table = table.sort_values(by=sort_column, ascending=ascending)


# -----------------------------------------
# PLAYER ANALYSIS MODE
# -----------------------------------------
def build_player_breakdown(web_name: str, gw1: int, gw2: int):
    row = players[players["web_name"] == web_name]
    if row.empty:
        return {"has_data": False}

    pid = int(row["id"].iloc[0])
    pos = row["Position"].iloc[0]

    history = weekly.get(str(pid), [])
    if not history:
        return {"has_data": False}

    df = pd.DataFrame(history)
    df = df[(df["round"] >= gw1) & (df["round"] <= gw2)]
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
    minutes_pts = 0
    for m in df["minutes"]:
        if m >= 60:
            minutes_pts += 2
        elif m > 0:
            minutes_pts += 1

    # Goal points
    goal_pts_map = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
    goal_pts = goals * goal_pts_map[pos]

    assist_pts = assists * 3

    # Clean sheet points
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

    # Defensive contribution
    if pos == "DEF":
        dc_pts = 2 if dc_raw >= 10 else 0
    elif pos in ["MID", "FWD"]:
        dc_pts = 2 if dc_raw >= 12 else 0
    else:
        dc_pts = 0

    accounted = (
        minutes_pts + goal_pts + assist_pts + cs_pts +
        save_pts + gc_pts + yc_pts + rc_pts +
        og_pts + pm_pts + ps_pts + dc_pts + bonus
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

    breakdown_df = pd.DataFrame(rows, columns=["Category", "Points"])
    if total_pts > 0:
        breakdown_df["% of Total"] = (breakdown_df["Points"] / total_pts * 100).round(1)
    else:
        breakdown_df["% of Total"] = 0

    return {
        "has_data": True,
        "name": web_name,
        "position": pos,
        "row": row,
        "history_df": df,
        "breakdown_df": breakdown_df,
        "total_points": total_pts,
    }



# -----------------------------------------
# FULLSCREEN OVERLAY MODE
# -----------------------------------------
if playerA != "None":
    # Exit button (top-right)
    st.markdown(
        """
        <div class="exit-button-container">
            <button id="exit_overlay_button" class="exit-btn">⬅ Exit Analysis Mode</button>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Hidden exit trigger
    if st.button("hidden_exit", key="hidden_exit_btn", help="", type="secondary"):
        pass

    # Real exit logic triggered by either visible button or ESC key
    if st.session_state.get("exit_triggered", False) or st.query_params.get("close", None):
        st.session_state.clear()
        st.session_state.selected_player = "None"
        st.session_state.selected_player2 = "None"
        st.rerun()

    # JS to link visible button to hidden Streamlit button
    st.markdown(
        """
        <script>
        const exitButton = window.parent.document.querySelector('#exit_overlay_button');
        exitButton.addEventListener('click', function() {
            const hiddenBtn = window.parent.document.querySelector('button[kind="secondary"]');
            hiddenBtn.click();
        });
        </script>
        """,
        unsafe_allow_html=True,
    )

    # Page UI
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)
    st.title("📌 FPL Player Analysis")

    if st.button("⬅ Back to main dashboard (Reset All Filters)", type="primary"):
        st.session_state.clear()
        st.session_state.selected_player = "None"
        st.session_state.selected_player2 = "None"
        st.rerun()

    A = build_player_breakdown(playerA, gw_start, gw_end)
    B = None
    if playerB != "None" and playerB != playerA:
        B = build_player_breakdown(playerB, gw_start, gw_end)
        if not B["has_data"]:
            B = None

    # Radar chart if comparison
    if B:
        st.subheader("📈 Radar: FPL Points Profile")

        categories = [
            "Goals", "Assists", "Clean Sheets", "Bonus", "Saves",
            "Defensive Contributions", "Minutes", "Total Points"
        ]

        def radar_vals(P):
            b = P["breakdown_df"].set_index("Category")["Points"]
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
        fig.add_trace(go.Scatterpolar(r=rA, theta=categories, fill="toself", name=A["name"]))
        fig.add_trace(go.Scatterpolar(r=rB, theta=categories, fill="toself", name=B["name"]))
        fig.update_layout(
            title="FPL Points Radar (GW Range)",
            showlegend=True,
            polar=dict(radialaxis=dict(visible=True))
        )
        st.plotly_chart(fig, use_container_width=True)

    # Points contribution
    st.subheader("🧮 FPL Points Contribution")

    if B:
        dfA = A["breakdown_df"].rename(columns={"Points": f"{A['name']} Points", "% of Total": f"{A['name']} %"})
        dfB = B["breakdown_df"].rename(columns={"Points": f"{B['name']} Points", "% of Total": f"{B['name']} %"})
        merged = dfA.merge(dfB, on="Category", how="outer").fillna(0)

        point_cols = [f"{A['name']} Points", f"{B['name']} Points"]

        def highlight(row):
            if row[point_cols[0]] > row[point_cols[1]]:
                return ["background-color:#c7f7c7", ""]
            elif row[point_cols[1]] > row[point_cols[0]]:
                return ["", "background-color:#c7f7c7"]
            else:
                return ["", ""]

        styled = merged.style.apply(highlight, axis=1, subset=point_cols)
        st.dataframe(styled, hide_index=True, width="stretch")

    else:
        st.dataframe(A["breakdown_df"], hide_index=True, width="stretch")

    # Gameweek breakdown
    st.subheader(f"📊 Points Breakdown by Gameweek — {A['name']}")

    dfh = A["history_df"]
    cols = [
        ("round", "Gameweek"),
        ("total_points", "Points"),
        ("goals_scored", "Goals"),
        ("assists", "Assists"),
        ("bonus", "Bonus"),
        ("minutes", "Minutes"),
        ("yellow_cards", "Yellow Cards"),
        ("red_cards", "Red Cards"),
    ]

    if A["position"] in ["GK", "DEF", "MID"]:
        cols.insert(4, ("clean_sheets", "Clean Sheets"))
        cols.insert(5, ("goals_conceded", "Goals Conceded"))

    if A["position"] == "GK":
        cols.append(("saves", "Saves"))

    df_show = dfh[[c[0] for c in cols]].rename(columns={a: b for a, b in cols})
    df_show = df_show.sort_values("Gameweek")

    st.dataframe(df_show, hide_index=True, width="stretch")

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# -----------------------------------------
# MAIN DASHBOARD
# -----------------------------------------
st.markdown("<div class='main-container'>", unsafe_allow_html=True)

st.title("🔥 FPL Analytics Dashboard")
st.write("Using cached local data for instant loading.")

st.subheader("📊 Player Value Table")
st.dataframe(
    table,
    hide_index=True,
    width="stretch",
)

st.markdown("</div>", unsafe_allow_html=True)
