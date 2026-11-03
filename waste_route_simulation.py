import streamlit as st
import pandas as pd
import folium
import math
import random
import time

from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
from folium.plugins import PolyLineTextPath


# =====================================================
# PAGE SETTINGS
# =====================================================

st.set_page_config(
    page_title="Rural Waste Management",
    page_icon="♻️",
    layout="wide"
)

st.title("♻️ Sustainable Rural Waste Management System")
st.caption("Smart Bin Monitoring | Route Optimisation | Truck Tracking")


# =====================================================
# CONSTANTS
# =====================================================

DEPOT = (16.3067, 80.4365)

TOTAL_BINS = 49
LIMIT = 80
NEAR_LIMIT = 70

BIN_IDS = [f"APNAMB{i:03d}" for i in range(1, 50)]


# =====================================================
# SESSION STATE
# =====================================================

def initialise():

    if "bins" not in st.session_state:

        st.session_state.bins = []

        for i in range(TOTAL_BINS):

            row = i // 7
            col = i % 7

            st.session_state.bins.append({
                "Bin ID": BIN_IDS[i],
                "Latitude": DEPOT[0] + (row - 3) * 0.003,
                "Longitude": DEPOT[1] + (col - 3) * 0.003,
                "Fill Level": random.randint(10, 100),
                "Collected": False,
                "Maintenance": False,
                "Reason": ""
            })

    defaults = {
    "route": [],
    "normal_route": [],
    "optimised_route": [],
    "running": False,
    "paused": False,
    "completed": False,
    "leg": 0,
    "fraction": 0.0,
    "last_tick": time.monotonic(),
    "stop_until": 0.0,
    "truck_position": DEPOT,
    "collected": [],
    "route_distance": 0.0,
    "map_version": 0
}

    for key, value in defaults.items():

        if key not in st.session_state:
            st.session_state[key] = value


initialise()


# =====================================================
# DISTANCE CALCULATION
# =====================================================

def distance(a, b):

    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    x = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return 6371 * 2 * math.atan2(
        math.sqrt(x),
        math.sqrt(1 - x)
    )


def coordinates():

    return {
        b["Bin ID"]: (b["Latitude"], b["Longitude"])
        for b in st.session_state.bins
    }


COORDS = coordinates()


# =====================================================
# BIN STATUS
# =====================================================

def status(b):

    if b["Maintenance"]:
        return "Maintenance"

    if b["Collected"]:
        return "Collected"

    if b["Fill Level"] >= LIMIT:
        return "Requires Collection"

    if b["Fill Level"] >= NEAR_LIMIT:
        return "Near Full"

    return "Normal"


def eligible_bins(include_near):

    result = []

    for b in st.session_state.bins:

        if b["Maintenance"] or b["Collected"]:
            continue

        if b["Fill Level"] >= LIMIT:
            result.append(b["Bin ID"])

        elif include_near and b["Fill Level"] >= NEAR_LIMIT:
            result.append(b["Bin ID"])

    return result


# =====================================================
# ROUTE CALCULATION
# =====================================================

def route_distance(route):

    if not route:
        return 0.0

    total = 0.0
    previous = DEPOT

    for bin_id in route:

        current = COORDS[bin_id]

        total += distance(previous, current)
        previous = current

    # Return from the last bin to the depot
    total += distance(previous, DEPOT)

    return total
def calculate_trip_details(route):

    total_distance = route_distance(route)

    travel_time = (
        total_distance / average_speed
    ) * 60

    fuel_used = total_distance / mileage

    fuel_cost = fuel_used * fuel_price

    return {
        "Distance": total_distance,
        "Travel Time": travel_time,
        "Fuel Used": fuel_used,
        "Fuel Cost": fuel_cost
    }

def nearest_neighbour(start, bin_ids):

    remaining = set(bin_ids)
    remaining.discard(start)

    route = [start]
    current = start

    while remaining:

        nxt = min(
            remaining,
            key=lambda x: distance(
                COORDS[current],
                COORDS[x]
            )
        )

        route.append(nxt)
        remaining.remove(nxt)
        current = nxt

    return route


def two_opt(route):

    best = route[:]

    if len(best) < 4:
        return best

    improved = True

    while improved:

        improved = False
        old_distance = route_distance(best)

        for i in range(1, len(best) - 2):

            for j in range(i + 1, len(best)):

                candidate = (
                    best[:i]
                    + best[i:j + 1][::-1]
                    + best[j + 1:]
                )

                new_distance = route_distance(candidate)

                if new_distance < old_distance:

                    best = candidate
                    old_distance = new_distance
                    improved = True

    return best


def best_start(bin_ids):

    if not bin_ids:
        return None, []

    best = None
    best_route = []
    shortest = float("inf")

    for start in bin_ids:

        candidate = nearest_neighbour(start, bin_ids)
        d = route_distance(candidate)

        if d < shortest:

            shortest = d
            best = start
            best_route = candidate

    return best, two_opt(best_route)


# =====================================================
# RESET AND COLLECTION
# =====================================================

def reset_truck(clear_route=False):

    st.session_state.running = False
    st.session_state.paused = False
    st.session_state.completed = False

    st.session_state.leg = 0
    st.session_state.fraction = 0.0

    st.session_state.last_tick = time.monotonic()
    st.session_state.stop_until = 0.0

    st.session_state.truck_position = DEPOT
    st.session_state.collected = []

    if clear_route:

        st.session_state.route = []
        st.session_state.route_distance = 0.0


def collect_bin(bin_id):

    for b in st.session_state.bins:

        if b["Bin ID"] == bin_id:

            b["Fill Level"] = 0
            b["Collected"] = True

            if bin_id not in st.session_state.collected:
                st.session_state.collected.append(bin_id)

            break


# =====================================================
# SIDEBAR
# =====================================================

# =====================================================
# SIDEBAR
# =====================================================

st.sidebar.header("Simulation Controls")

speed = st.sidebar.slider(
    "Truck Animation Speed",
    1, 10, 10
)

include_near = st.sidebar.checkbox(
    "Include near-full bins",
    value=False
)

st.sidebar.divider()
st.sidebar.subheader("Travel & Fuel Settings")

average_speed = st.sidebar.number_input(
    "Average truck speed (km/hour)",
    min_value=5.0,
    max_value=100.0,
    value=20.0,
    step=5.0
)

mileage = st.sidebar.number_input(
    "Truck mileage (km/litre)",
    min_value=1.0,
    max_value=100.0,
    value=15.0,
    step=1.0
)

fuel_price = st.sidebar.number_input(
    "Diesel price (₹/litre)",
    min_value=1.0,
    max_value=200.0,
    value=95.0,
    step=1.0
)


# =====================================================
# DASHBOARD
# =====================================================

bins = st.session_state.bins

counts = {
    "Collection": sum(status(b) == "Requires Collection" for b in bins),
    "Near": sum(status(b) == "Near Full" for b in bins),
    "Maintenance": sum(status(b) == "Maintenance" for b in bins),
    "Collected": sum(status(b) == "Collected" for b in bins)
}

st.subheader("Waste Monitoring Dashboard")

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Total Bins", TOTAL_BINS)
c2.metric("Requires Collection", counts["Collection"])
c3.metric("Near Full", counts["Near"])
c4.metric("Maintenance", counts["Maintenance"])
c5.metric("Collected", counts["Collected"])


# =====================================================
# BIN DETAILS
# =====================================================

st.divider()

left, right = st.columns(2)

with left:

    st.subheader("Individual Bin Details")

    selected = st.selectbox(
        "Select Bin",
        BIN_IDS,
        key="details_bin"
    )

    data = next(
        b for b in bins
        if b["Bin ID"] == selected
    )

    st.write("**Bin ID:**", data["Bin ID"])
    st.write("**Fill Level:**", f'{data["Fill Level"]}%')
    st.write("**Status:**", status(data))

    st.progress(data["Fill Level"] / 100)

with right:

    st.subheader("Bin Maintenance")

    selected_maintenance = st.selectbox(
        "Select Bin for Maintenance",
        BIN_IDS,
        key="maintenance_bin"
    )

    maintenance_data = next(
        b for b in bins
        if b["Bin ID"] == selected_maintenance
    )

    if maintenance_data["Maintenance"]:

        st.warning("Bin is under maintenance.")

        st.write("Reason:", maintenance_data["Reason"])

        if st.button("Restore Bin"):

            maintenance_data["Maintenance"] = False
            maintenance_data["Reason"] = ""

            reset_truck(clear_route=True)

            st.rerun()

    else:

        reason = st.selectbox(
            "Maintenance Reason",
            [
                "Damaged Bin",
                "Sensor Failure",
                "Communication Failure",
                "Bin Cleaning",
                "Other"
            ]
        )

        if st.button("Report Maintenance"):

            maintenance_data["Maintenance"] = True
            maintenance_data["Reason"] = reason

            reset_truck(clear_route=True)

            st.rerun()


# =====================================================
# ROUTE GENERATION
# =====================================================

# =====================================================
# ROUTE GENERATION AND OPTIMISATION COMPARISON
# =====================================================

st.divider()

st.subheader("Route Optimisation")

eligible = eligible_bins(include_near)

if eligible:

    recommended, recommended_route = best_start(eligible)

    st.write("Recommended Starting Bin:", recommended)

    start = st.selectbox(
        "Choose Starting Bin",
        eligible,
        index=eligible.index(recommended)
    )

    if st.button("Generate Route", type="primary"):

        # Normal route: bins in their original order
        normal_route = eligible[:]

        # Optimised route: nearest neighbour + 2-opt
        optimised_route = nearest_neighbour(start, eligible)
        optimised_route = two_opt(optimised_route)

        reset_truck(clear_route=False)

        st.session_state.route = optimised_route

        st.session_state.normal_route = normal_route
        st.session_state.optimised_route = optimised_route

        st.session_state.route_distance = route_distance(
            optimised_route
        )

        st.session_state.map_version += 1

        st.rerun()

else:

    st.info("No bins currently require collection.")
    # =====================================================
# NORMAL VS OPTIMISED ROUTE COMPARISON
# =====================================================

if st.session_state.route:

    st.divider()

    st.subheader("Normal Route vs Optimised Route")

    normal_route = st.session_state.normal_route
    optimised_route = st.session_state.optimised_route

    normal = calculate_trip_details(normal_route)
    optimised = calculate_trip_details(optimised_route)

    distance_saved = normal["Distance"] - optimised["Distance"]
    time_saved = normal["Travel Time"] - optimised["Travel Time"]
    fuel_saved = normal["Fuel Used"] - optimised["Fuel Used"]
    cost_saved = normal["Fuel Cost"] - optimised["Fuel Cost"]

    comparison = pd.DataFrame({
        "Parameter": [
            "Total Distance (km)",
            "Travel Time (minutes)",
            "Fuel Used (litres)",
            "Fuel Cost (₹)"
        ],
        "Normal Route": [
            normal["Distance"],
            normal["Travel Time"],
            normal["Fuel Used"],
            normal["Fuel Cost"]
        ],
        "Optimised Route": [
            optimised["Distance"],
            optimised["Travel Time"],
            optimised["Fuel Used"],
            optimised["Fuel Cost"]
        ],
        "Savings": [
            distance_saved,
            time_saved,
            fuel_saved,
            cost_saved
        ]
    })

    st.dataframe(
        comparison.round(2),
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Benefits of Route Optimisation")

    x1, x2, x3, x4 = st.columns(4)

    x1.metric(
        "Distance Saved",
        f"{distance_saved:.2f} km"
    )

    x2.metric(
        "Time Saved",
        f"{time_saved:.2f} min"
    )

    x3.metric(
        "Fuel Saved",
        f"{fuel_saved:.2f} L"
    )

    x4.metric(
        "Money Saved",
        f"₹{cost_saved:.2f}"
    )

    if normal["Distance"] > 0:

        saving_percentage = (
            distance_saved / normal["Distance"]
        ) * 100

        st.success(
            f"Route optimisation reduced the estimated "
            f"travel distance by {saving_percentage:.2f}%."
        )

    st.subheader("Optimised Collection Sequence")

    st.write("Depot → " + " → ".join(optimised_route) + " → Depot")
# =====================================================
# ROUTE TABLE
# =====================================================

# =====================================================
# OPTIMISED ROUTE TABLE
# =====================================================

route = st.session_state.route

if route:

    st.subheader("Optimised Collection Sequence")

    rows = []
    previous = DEPOT

    for i, bin_id in enumerate(route):

        current = COORDS[bin_id]

        rows.append({
            "Stop": i + 1,
            "From": "Depot" if i == 0 else route[i - 1],
            "To Bin": bin_id,
            "Distance (km)": round(
                distance(previous, current), 3
            )
        })

        previous = current

    # Add the return journey
    rows.append({
        "Stop": len(route) + 1,
        "From": route[-1],
        "To Bin": "Depot",
        "Distance (km)": round(
            distance(previous, DEPOT), 3
        )
    })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True
    )

    details = calculate_trip_details(route)

    a, b, c, d = st.columns(4)

    a.metric(
        "Total Distance",
        f'{details["Distance"]:.2f} km'
    )

    b.metric(
        "Travel Time",
        f'{details["Travel Time"]:.2f} min'
    )

    c.metric(
        "Fuel Required",
        f'{details["Fuel Used"]:.2f} L'
    )

    d.metric(
        "Fuel Cost",
        f'₹{details["Fuel Cost"]:.2f}'
    )

    st.caption(
        "Estimates use the average speed, mileage and diesel price "
        "specified in the sidebar. They do not include collection "
        "stops, traffic delays or actual road distances."
    )

# =====================================================
# TRUCK CONTROLS
# =====================================================

# =====================================================
# TRUCK CONTROLS
# =====================================================

st.divider()
st.subheader("Live Truck Tracking")

if route:

    a, b, c = st.columns(3)

    if a.button("Start / Resume", use_container_width=True):

        if not st.session_state.completed:
            st.session_state.running = True
            st.session_state.paused = False
            st.session_state.last_tick = time.monotonic()
            st.rerun()

    if b.button("Pause", use_container_width=True):

        st.session_state.running = False
        st.session_state.paused = True
        st.rerun()

    if c.button("Reset Truck", use_container_width=True):

        reset_truck(clear_route=False)
        st.rerun()

    if st.session_state.running:

        now = time.monotonic()

        if now >= st.session_state.stop_until:

            if st.session_state.leg < len(route):

                target_id = route[st.session_state.leg]
                target = COORDS[target_id]

                start_position = (
                    DEPOT
                    if st.session_state.leg == 0
                    else COORDS[route[st.session_state.leg - 1]]
                )

                elapsed = min(
                    max(now - st.session_state.last_tick, 0),
                    0.5
                )

                st.session_state.last_tick = now

                duration = max(0.18, 1.25 - speed * 0.105)

                st.session_state.fraction += elapsed / duration

                if st.session_state.fraction >= 1:

                    # Reach the current target bin
                    st.session_state.truck_position = target

                    # Collect this bin
                    collect_bin(target_id)

                    # Move to the next bin on the following refresh
                    st.session_state.leg += 1
                    st.session_state.fraction = 0.0

                    # Pause for 0.1 seconds
                    st.session_state.stop_until = time.monotonic() + 0.1
                    st.session_state.last_tick = time.monotonic()

                else:

                    f = st.session_state.fraction

                    st.session_state.truck_position = (
                        start_position[0] +
                        f * (target[0] - start_position[0]),

                        start_position[1] +
                        f * (target[1] - start_position[1])
                    )

            else:

                st.session_state.running = False
                st.session_state.completed = True

        else:

            st.session_state.last_tick = now

        if st.session_state.leg >= len(route):

            st.session_state.running = False
            st.session_state.completed = True

    if st.session_state.completed:
        st.success("All bins collected successfully!")

    elif st.session_state.paused:
        st.warning("Truck is paused.")

    elif st.session_state.running:
        st.info("Truck is moving.")

    if st.session_state.leg < len(route):

        st.write(
            "**Current Target:**",
            route[st.session_state.leg]
        )

    else:

        st.write("**Current Target:** All bins collected")

    st.write(
        f"**Collected:** {len(st.session_state.collected)} / {len(route)}"
    )

    st.progress(
        len(st.session_state.collected) / len(route)
    )

# =====================================================
# MAP DISPLAY
# =====================================================

# =====================================================
# MAP DISPLAY
# =====================================================

st.divider()
st.subheader("Waste Collection Map")

all_points = [DEPOT] + [
    (b["Latitude"], b["Longitude"])
    for b in bins
]

m = folium.Map(
    location=DEPOT,
    zoom_start=14,
    tiles="OpenStreetMap",
    control_scale=True
)

# Depot marker
folium.Marker(
    DEPOT,
    tooltip="Collection Depot",
    popup="Waste Collection Depot",
    icon=folium.Icon(
        color="blue",
        icon="home",
        prefix="fa"
    )
).add_to(m)


# Optimised route line
if route:

    route_points = [DEPOT] + [
        COORDS[bin_id] for bin_id in route
    ] + [DEPOT]

    line = folium.PolyLine(
        route_points,
        color="red",
        weight=5,
        opacity=0.9,
        tooltip="Optimised Collection Route"
    ).add_to(m)

    PolyLineTextPath(
        line,
        "  ➤  ",
        repeat=True,
        offset=8,
        attributes={
            "fill": "red",
            "font-weight": "bold",
            "font-size": "18"
        }
    ).add_to(m)

    m.fit_bounds(route_points, padding=(30, 30))

else:

    m.fit_bounds(all_points, padding=(30, 30))


# =====================================================
# DISPLAY ALL 49 VIRTUAL BIN MARKERS
# =====================================================

for b in bins:

    s = status(b)

    colour = {
        "Normal": "green",
        "Near Full": "orange",
        "Requires Collection": "red",
        "Collected": "purple",
        "Maintenance": "gray"
    }[s]

    folium.Marker(
        location=(b["Latitude"], b["Longitude"]),

        tooltip=(
            f'{b["Bin ID"]} | '
            f'Fill Level: {b["Fill Level"]}% | '
            f'Status: {s}'
        ),

        popup=folium.Popup(
            f"""
            <b>Bin ID:</b> {b["Bin ID"]}<br>
            <b>Fill Level:</b> {b["Fill Level"]}%<br>
            <b>Status:</b> {s}<br>
            <b>Latitude:</b> {b["Latitude"]}<br>
            <b>Longitude:</b> {b["Longitude"]}
            """,
            max_width=250
        ),

        icon=folium.Icon(
            color=colour,
            icon="trash",
            prefix="fa"
        )

    ).add_to(m)


# =====================================================
# TRUCK MARKER
# =====================================================

folium.Marker(
    location=st.session_state.truck_position,

    tooltip="Collection Truck",

    popup="Waste Collection Truck",

    icon=folium.DivIcon(
        html="""
        <div style="
            font-size: 28px;
            width: 35px;
            text-align: center;
        ">🚛</div>
        """
    )

).add_to(m)


# =====================================================
# DISPLAY MAP IN STREAMLIT
# =====================================================

st_folium(
    m,
    width=None,
    height=600,
    key=f"waste_map_{st.session_state.map_version}"
)

# =====================================================
# DISTANCE TABLES
# =====================================================

with st.expander("Bin-to-Depot Distances"):

    rows = []

    for b in bins:

        rows.append({
            "Bin ID": b["Bin ID"],
            "Distance (km)": round(
                distance(
                    DEPOT,
                    (b["Latitude"], b["Longitude"])
                ), 3
            )
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True
    )


with st.expander("49 × 49 Distance Matrix"):

    matrix = []

    for bin1 in BIN_IDS:

        row = {"Bin ID": bin1}

        for bin2 in BIN_IDS:

            row[bin2] = round(
                distance(COORDS[bin1], COORDS[bin2]), 3
            )

        matrix.append(row)

    st.dataframe(
        pd.DataFrame(matrix),
        use_container_width=True,
        height=450
    )


# =====================================================
# ALL BIN DETAILS AND REPORT
# =====================================================

st.divider()

st.subheader("All Bin Details")

report = pd.DataFrame([
    {
        "Bin ID": b["Bin ID"],
        "Fill Level": b["Fill Level"],
        "Status": status(b),
        "Latitude": b["Latitude"],
        "Longitude": b["Longitude"],
        "Maintenance Reason": b["Reason"]
    }
    for b in bins
])

st.dataframe(
    report,
    use_container_width=True,
    hide_index=True
)

st.download_button(
    "Download CSV Report",
    data=report.to_csv(index=False).encode("utf-8"),
    file_name="waste_management_report.csv",
    mime="text/csv"
)


# =====================================================
# NEXT DAY SIMULATION
# =====================================================

st.divider()

if st.button("Simulate Next Day"):

    reset_truck(clear_route=True)

    for b in bins:

        if not b["Maintenance"]:

            b["Collected"] = False
            b["Fill Level"] = random.randint(10, 100)

    st.rerun()


# =====================================================
# AUTO REFRESH
# =====================================================

if st.session_state.running:

    st_autorefresh(
        interval=250,
        key="truck_refresh"
    )
    #python -m streamlit run waste_route_simulation.py