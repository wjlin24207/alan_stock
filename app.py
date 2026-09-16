import os
import tempfile

import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go
import skrf as rf
import streamlit as st

st.set_page_config(page_title="Smith Chart Tool", layout="wide")
TYPES = ["Series L", "Series C", "Shunt L", "Shunt C"]
SCALE = {"nH": 1e-9, "uH": 1e-6, "pF": 1e-12, "nF": 1e-9}


def init_state():
    st.session_state.setdefault("components", [])
    st.session_state.setdefault("selected_component", None)
    st.session_state.setdefault("markers", [1.0])


def read_touchstone(upload):
    suffix = os.path.splitext(upload.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(upload.getbuffer())
        name = tmp.name
    try:
        network = rf.Network(name)
    finally:
        os.unlink(name)
    if network.nports > 3:
        raise ValueError("Only S1P, S2P, and S3P are supported.")
    return network


def gamma_to_z(gamma, z0):
    with np.errstate(divide="ignore", invalid="ignore"):
        return z0 * (1 + gamma) / (1 - gamma)


def metrics(gamma):
    magnitude = np.abs(gamma)
    db = 20 * np.log10(np.maximum(magnitude, 1e-15))
    vswr = np.where(magnitude < 1, (1 + magnitude) / np.maximum(1 - magnitude, 1e-15), np.inf)
    return db, vswr


def s_to_z(s_matrix, z0):
    count, ports, _ = s_matrix.shape
    identity = np.eye(ports, dtype=complex)
    result = np.empty_like(s_matrix, dtype=complex)
    for k in range(count):
        result[k] = z0 * np.linalg.solve((identity - s_matrix[k]).T, (identity + s_matrix[k]).T).T
    return result


def z_to_s(z_matrix, z0):
    count, ports, _ = z_matrix.shape
    identity = np.eye(ports, dtype=complex)
    result = np.empty_like(z_matrix, dtype=complex)
    for k in range(count):
        numerator = z_matrix[k] - z0 * identity
        denominator = z_matrix[k] + z0 * identity
        result[k] = np.linalg.solve(denominator.T, numerator.T).T
    return result


def touchstone_matching(s_matrix, frequency, components, port, z0):
    z_matrix = s_to_z(s_matrix, z0)
    omega = 2 * np.pi * frequency
    for item in components:
        value = item["value_si"]
        if item["kind"] == "Series L":
            z_matrix[:, port, port] += 1j * omega * value
        elif item["kind"] == "Series C":
            z_matrix[:, port, port] += 1 / (1j * omega * value)
        else:
            for k, w in enumerate(omega):
                y_matrix = np.linalg.inv(z_matrix[k])
                element_y = 1 / (1j * w * value) if item["kind"] == "Shunt L" else 1j * w * value
                y_matrix[port, port] += element_y
                z_matrix[k] = np.linalg.inv(y_matrix)
    return z_to_s(z_matrix, z0)


def standalone_lc(frequency, components, z0):
    omega = 2 * np.pi * frequency
    result = np.zeros((len(frequency), 2, 2), dtype=complex)
    for k, w in enumerate(omega):
        total = np.eye(2, dtype=complex)
        for item in components:
            value = item["value_si"]
            if item["kind"] == "Series L":
                element = np.array([[1, 1j * w * value], [0, 1]], complex)
            elif item["kind"] == "Series C":
                element = np.array([[1, 1 / (1j * w * value)], [0, 1]], complex)
            elif item["kind"] == "Shunt L":
                element = np.array([[1, 0], [1 / (1j * w * value), 1]], complex)
            else:
                element = np.array([[1, 0], [1j * w * value, 1]], complex)
            total = total @ element
        a, b, c, d = total.ravel()
        den = a + b / z0 + c * z0 + d
        result[k, 0, 0] = (a + b / z0 - c * z0 - d) / den
        result[k, 1, 0] = 2 / den
        result[k, 0, 1] = 2 * (a * d - b * c) / den
        result[k, 1, 1] = (-a + b / z0 - c * z0 + d) / den
    return result


def trace(matrix, name):
    return matrix[:, int(name[1]) - 1, int(name[2]) - 1]


def smith_plot(original, matched, marker_indices, standalone):
    fig, ax = plt.subplots(figsize=(8, 8))
    rf.plotting.smith(smithR=1, chart_type="z", draw_labels=False, ax=ax)
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for index, (name, values) in enumerate(original.items()):
        color = colors[index % len(colors)]
        label = name if standalone else f"Original {name}"
        ax.plot(values.real, values.imag, lw=2, color=color, label=label)
        for marker_number, point_index in enumerate(marker_indices, 1):
            ax.scatter(values[point_index].real, values[point_index].imag, s=55, color=color, zorder=5)
            ax.annotate(f"M{marker_number}", (values[point_index].real, values[point_index].imag), xytext=(5, 5), textcoords="offset points", color=color)
        if name in matched:
            values2 = matched[name]
            ax.plot(values2.real, values2.imag, "--", lw=2, color=color, label=f"Matched {name}")
            for marker_number, point_index in enumerate(marker_indices, 1):
                ax.scatter(values2[point_index].real, values2[point_index].imag, marker="x", s=65, color=color, zorder=6)
    ax.legend(fontsize=8)
    ax.set_title("Smith Chart")
    ax.grid(False)
    fig.subplots_adjust(left=.05, right=.97, bottom=.05, top=.92)
    return fig


def component_name(item, index):
    suffix = " to GND" if item["kind"].startswith("Shunt") else ""
    symbol = "L" if item["kind"].endswith("L") else "C"
    return f"{index + 1}. {symbol}{suffix}\n\n{item['value']:g} {item['unit']}"


init_state()
st.title("Streamlit Smith Chart Tool")
st.caption("Version 8.2 - Multiple manual markers, no export section, 0.1 component steps")

with st.sidebar:
    st.header("1. Simulation source")
    mode = st.radio("Mode", ["Touchstone file", "Standalone LC network"])
    uploaded = st.file_uploader("Upload S1P/S2P/S3P", type=["s1p", "s2p", "s3p"]) if mode == "Touchstone file" else None
    z0 = st.number_input("Z0 (ohm)", 1.0, 1000.0, 50.0, 1.0)

if mode == "Touchstone file" and uploaded is None:
    st.info("Upload a Touchstone file or select Standalone LC network.")
    st.stop()

if mode == "Touchstone file":
    try:
        ntwk = read_touchstone(uploaded)
    except Exception as exc:
        st.error(f"Cannot read Touchstone file: {exc}")
        st.stop()
    full_f = ntwk.f / 1e9
    full_s = ntwk.s
    ports = ntwk.nports
    lower, upper = float(full_f.min()), float(full_f.max())
    with st.sidebar:
        st.success(f"{uploaded.name}: {ports}-port, {len(full_f)} points")
        st.header("2. Frequency range")
        a, b = st.columns(2)
        start = a.number_input("Start GHz", lower, upper, lower, format="%.6f")
        stop = b.number_input("Stop GHz", lower, upper, upper, format="%.6f")
    if start >= stop:
        st.error("Start frequency must be smaller than stop frequency.")
        st.stop()
    mask = (full_f >= start) & (full_f <= stop)
    f_ghz, s = full_f[mask], full_s[mask]
else:
    ports = 2
    with st.sidebar:
        st.header("2. Frequency range")
        a, b = st.columns(2)
        start = a.number_input("Start GHz", min_value=0.000001, value=0.1, step=0.1, format="%.6f")
        stop = b.number_input("Stop GHz", min_value=0.000002, value=10.0, step=0.1, format="%.6f")
        points = st.number_input("Points", 2, 10001, 1001, 1)
    if start >= stop:
        st.error("Start frequency must be smaller than stop frequency.")
        st.stop()
    f_ghz = np.linspace(start, stop, int(points))
    s = None
f_hz = f_ghz * 1e9

all_names = [f"S{i+1}{j+1}" for i in range(ports) for j in range(ports)]
ref_names = [f"S{i+1}{i+1}" for i in range(ports)]
with st.sidebar:
    st.header("3. Display")
    smith_names = st.multiselect("Smith Chart", ref_names, default=[ref_names[0]]) or [ref_names[0]]
    log_names = st.multiselect("Log Magnitude", all_names, default=["S11", "S21"] if ports >= 2 else ["S11"]) or [all_names[0]]
    if mode == "Touchstone file":
        match_name = st.selectbox("Matching port", ref_names)
        port = int(match_name[1]) - 1
    else:
        match_name, port = "S11", 0

    st.header("4. Markers")
    marker_count = st.number_input("Number of markers", min_value=1, max_value=20, value=len(st.session_state.markers), step=1)
    marker_values = []
    for index in range(int(marker_count)):
        default = st.session_state.markers[index] if index < len(st.session_state.markers) else start + (stop - start) * (index + 1) / (int(marker_count) + 1)
        default = min(max(float(default), float(start)), float(stop))
        marker_values.append(st.number_input(f"M{index + 1} frequency (GHz)", min_value=float(start), max_value=float(stop), value=default, step=0.001, format="%.6f", key=f"marker_{index}"))
    st.session_state.markers = marker_values

marker_indices = [int(np.argmin(np.abs(f_ghz - item))) for item in marker_values]

st.subheader("Matching network")
a, b, c, d = st.columns([1.2, 1, 1, 1])
kind = a.selectbox("Element", TYPES)
value = b.number_input("Value", min_value=0.1, value=2.2 if kind.endswith("L") else 1.0, step=0.1, format="%.1f")
units = ["nH", "uH"] if kind.endswith("L") else ["pF", "nF"]
unit = c.selectbox("Unit", units)
if d.button("Add element", type="primary", use_container_width=True):
    st.session_state.components.append({"kind": kind, "value": value, "unit": unit, "value_si": value * SCALE[unit]})
    st.session_state.selected_component = len(st.session_state.components) - 1
    st.rerun()

if st.session_state.components:
    widths = [1] + sum(([.25, 1.15] for _ in st.session_state.components), []) + [.25, 1]
    cols = st.columns(widths)
    cols[0].markdown("**DUT**" if mode == "Touchstone file" else "**Port 1**")
    position = 1
    for index, item in enumerate(st.session_state.components):
        cols[position].markdown("→")
        position += 1
        if cols[position].button(component_name(item, index), key=f"pick_{index}", use_container_width=True, type="primary" if st.session_state.selected_component == index else "secondary"):
            st.session_state.selected_component = index
            st.rerun()
        position += 1
    cols[position].markdown("→")
    cols[position + 1].markdown("**Port 2**" if mode == "Standalone LC network" else f"**Port {port + 1}**")

    selected = st.session_state.selected_component
    if selected is not None and selected < len(st.session_state.components):
        item = st.session_state.components[selected]
        st.markdown(f"#### Edit component {selected + 1}")
        e1, e2, e3 = st.columns(3)
        edit_kind = e1.selectbox("Type", TYPES, TYPES.index(item["kind"]), key=f"type_{selected}")
        edit_units = ["nH", "uH"] if edit_kind.endswith("L") else ["pF", "nF"]
        current_unit = item["unit"] if item["unit"] in edit_units else edit_units[0]
        edit_value = e2.number_input("Value", min_value=0.1, value=float(item["value"]), step=0.1, format="%.1f", key=f"value_{selected}")
        edit_unit = e3.selectbox("Unit", edit_units, edit_units.index(current_unit), key=f"unit_{selected}_{edit_kind}")
        q1, q2, q3, q4 = st.columns(4)
        if q1.button("Save", type="primary", use_container_width=True):
            st.session_state.components[selected] = {"kind": edit_kind, "value": edit_value, "unit": edit_unit, "value_si": edit_value * SCALE[edit_unit]}
            st.rerun()
        if q2.button("Move left", disabled=selected == 0, use_container_width=True):
            items = st.session_state.components
            items[selected - 1], items[selected] = items[selected], items[selected - 1]
            st.session_state.selected_component -= 1
            st.rerun()
        if q3.button("Move right", disabled=selected == len(st.session_state.components) - 1, use_container_width=True):
            items = st.session_state.components
            items[selected + 1], items[selected] = items[selected], items[selected + 1]
            st.session_state.selected_component += 1
            st.rerun()
        if q4.button("Delete", use_container_width=True):
            st.session_state.components.pop(selected)
            st.session_state.selected_component = min(selected, len(st.session_state.components) - 1) if st.session_state.components else None
            st.rerun()
    if st.button("Clear network"):
        st.session_state.components = []
        st.session_state.selected_component = None
        st.rerun()
else:
    st.info("Add at least one L/C element.")

try:
    if mode == "Standalone LC network":
        calculated_s = standalone_lc(f_hz, st.session_state.components, z0)
        original_s = None
    else:
        original_s = s
        calculated_s = touchstone_matching(s, f_hz, st.session_state.components, port, z0)
except Exception as exc:
    st.error(f"Simulation failed: {exc}")
    st.stop()

smith_original = {name: trace(calculated_s if mode == "Standalone LC network" else original_s, name) for name in smith_names}
smith_matched = {} if mode == "Standalone LC network" or not st.session_state.components else {name: trace(calculated_s, name) for name in smith_names}

left, right = st.columns([1.3, 1])
with left:
    fig = smith_plot(smith_original, smith_matched, marker_indices, mode == "Standalone LC network")
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)
with right:
    st.subheader("Marker values")
    for marker_number, point_index in enumerate(marker_indices, 1):
        st.markdown(f"**M{marker_number}: requested {marker_values[marker_number-1]:.6f} GHz, actual {f_ghz[point_index]:.6f} GHz**")
        gamma = trace(calculated_s, match_name)[point_index]
        impedance = gamma_to_z(gamma, z0)
        db, vswr = metrics(np.array([gamma]))
        st.write(f"Z = {impedance.real:.3f} {'+' if impedance.imag >= 0 else '-'} j{abs(impedance.imag):.3f} ohm; {match_name} = {db[0]:.2f} dB; VSWR = {vswr[0]:.3f}")
        for name in log_names:
            value_db = 20 * np.log10(max(abs(trace(calculated_s, name)[point_index]), 1e-15))
            st.write(f"{name}: {value_db:.2f} dB")

st.subheader("S-parameter Log Magnitude")
chart = go.Figure()
for name in log_names:
    if mode == "Touchstone file":
        values = trace(original_s, name)
        chart.add_trace(go.Scatter(x=f_ghz, y=20*np.log10(np.maximum(np.abs(values), 1e-15)), mode="lines", name=f"Original {name}"))
        if st.session_state.components:
            values2 = trace(calculated_s, name)
            chart.add_trace(go.Scatter(x=f_ghz, y=20*np.log10(np.maximum(np.abs(values2), 1e-15)), mode="lines", name=f"Matched {name}"))
    else:
        values = trace(calculated_s, name)
        chart.add_trace(go.Scatter(x=f_ghz, y=20*np.log10(np.maximum(np.abs(values), 1e-15)), mode="lines", name=name))
for marker_number, marker_frequency in enumerate(marker_values, 1):
    chart.add_vline(x=marker_frequency, line_width=1, line_dash="dot", annotation_text=f"M{marker_number}")
chart.update_layout(xaxis_title="Frequency (GHz)", yaxis_title="Log Magnitude (dB)", hovermode="x unified", margin=dict(l=20, r=20, t=20, b=20))
chart.update_xaxes(range=[float(f_ghz.min()), float(f_ghz.max())], fixedrange=True)
chart.update_yaxes(fixedrange=True)
st.plotly_chart(chart, use_container_width=True, config={"scrollZoom": False, "displaylogo": False, "modeBarButtonsToRemove": ["zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d", "autoScale2d"]})
