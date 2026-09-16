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
    if suffix not in {".s1p", ".s2p", ".s3p"}:
        raise ValueError("Only S1P, S2P, and S3P are supported.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(upload.getbuffer())
        path = tmp.name
    try:
        network = rf.Network(path)
        network.name = os.path.splitext(upload.name)[0]
    finally:
        os.unlink(path)
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


def trace(matrix, name):
    return matrix[:, int(name[1]) - 1, int(name[2]) - 1]


def s_to_z(s_matrix, z0):
    count, ports, _ = s_matrix.shape
    eye = np.eye(ports, dtype=complex)
    result = np.empty_like(s_matrix, dtype=complex)
    for k in range(count):
        result[k] = z0 * np.linalg.solve((eye - s_matrix[k]).T, (eye + s_matrix[k]).T).T
    return result


def z_to_s(z_matrix, z0):
    count, ports, _ = z_matrix.shape
    eye = np.eye(ports, dtype=complex)
    result = np.empty_like(z_matrix, dtype=complex)
    for k in range(count):
        result[k] = np.linalg.solve((z_matrix[k] + z0 * eye).T, (z_matrix[k] - z0 * eye).T).T
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
    result = np.zeros((len(frequency), 2, 2), dtype=complex)
    for k, w in enumerate(2 * np.pi * frequency):
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
        denominator = a + b / z0 + c * z0 + d
        result[k, 0, 0] = (a + b / z0 - c * z0 - d) / denominator
        result[k, 1, 0] = 2 / denominator
        result[k, 0, 1] = 2 * (a * d - b * c) / denominator
        result[k, 1, 1] = (-a + b / z0 - c * z0 + d) / denominator
    return result


def interpolate_complex(source_f, source_values, target_f):
    real = np.interp(target_f, source_f, np.real(source_values))
    imag = np.interp(target_f, source_f, np.imag(source_values))
    return real + 1j * imag


def common_comparison_data(networks, start_ghz, stop_ghz, points):
    target_ghz = np.linspace(start_ghz, stop_ghz, points)
    target_hz = target_ghz * 1e9
    matrices = []
    for network in networks:
        ports = network.nports
        matrix = np.empty((points, ports, ports), dtype=complex)
        for row in range(ports):
            for col in range(ports):
                matrix[:, row, col] = interpolate_complex(network.f, network.s[:, row, col], target_hz)
        matrices.append(matrix)
    return target_ghz, matrices


def smith_plot(datasets, names, marker_indices):
    fig, ax = plt.subplots(figsize=(8, 8))
    rf.plotting.smith(smithR=1, chart_type="z", draw_labels=False, ax=ax)
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    color_index = 0
    for dataset_name, matrix in datasets:
        for name in names:
            values = trace(matrix, name)
            color = colors[color_index % len(colors)]
            color_index += 1
            ax.plot(values.real, values.imag, lw=2, color=color, label=f"{dataset_name} {name}")
            for number, index in enumerate(marker_indices, 1):
                ax.scatter(values[index].real, values[index].imag, s=45, color=color, zorder=5)
                ax.annotate(f"M{number}", (values[index].real, values[index].imag), xytext=(4, 4), textcoords="offset points", color=color, fontsize=8)
    ax.legend(fontsize=8)
    ax.set_title("Smith Chart")
    ax.grid(False)
    fig.subplots_adjust(left=.05, right=.97, bottom=.05, top=.92)
    return fig


def fixed_plotly(fig):
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, use_container_width=True, config={
        "scrollZoom": False,
        "displaylogo": False,
        "modeBarButtonsToRemove": ["zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d", "autoScale2d"],
    })


def component_name(item, index):
    shunt = " to GND" if item["kind"].startswith("Shunt") else ""
    symbol = "L" if item["kind"].endswith("L") else "C"
    return f"{index + 1}. {symbol}{shunt}\n\n{item['value']:g} {item['unit']}"


init_state()
st.title("Streamlit Smith Chart Tool")
st.caption("Version 9.0 - Touchstone matching, standalone LC, and multi-file SnP comparison")

with st.sidebar:
    st.header("1. Simulation source")
    mode = st.radio("Mode", ["Touchstone matching", "Standalone LC network", "SnP file comparison"])
    z0 = st.number_input("Z0 (ohm)", 1.0, 1000.0, 50.0, 1.0)

# -------------------- SnP comparison mode --------------------
if mode == "SnP file comparison":
    with st.sidebar:
        uploads = st.file_uploader("Upload 2 or 3 SnP files", type=["s1p", "s2p", "s3p"], accept_multiple_files=True)
    if not uploads or len(uploads) < 2:
        st.info("Upload at least 2 SnP files for comparison.")
        st.stop()
    if len(uploads) > 3:
        st.error("A maximum of 3 SnP files is supported.")
        st.stop()
    try:
        networks = [read_touchstone(item) for item in uploads]
    except Exception as exc:
        st.error(f"Cannot read SnP file: {exc}")
        st.stop()
    port_counts = {network.nports for network in networks}
    if len(port_counts) != 1:
        st.error("All comparison files must have the same port count, such as all S2P or all S3P.")
        st.stop()
    ports = networks[0].nports
    overlap_start = max(network.f.min() for network in networks) / 1e9
    overlap_stop = min(network.f.max() for network in networks) / 1e9
    if overlap_start >= overlap_stop:
        st.error("The uploaded files do not have an overlapping frequency range.")
        st.stop()
    all_names = [f"S{i+1}{j+1}" for i in range(ports) for j in range(ports)]
    reflection_names = [f"S{i+1}{i+1}" for i in range(ports)]
    with st.sidebar:
        st.header("2. Comparison range")
        c1, c2 = st.columns(2)
        start = c1.number_input("Start GHz", overlap_start, overlap_stop, overlap_start, format="%.6f")
        stop = c2.number_input("Stop GHz", overlap_start, overlap_stop, overlap_stop, format="%.6f")
        points = st.number_input("Interpolation points", 2, 10001, 1001, 1)
        if start >= stop:
            st.error("Start frequency must be smaller than stop frequency.")
            st.stop()
        st.header("3. Comparison traces")
        smith_names = st.multiselect("Smith Chart", reflection_names, default=[reflection_names[0]]) or [reflection_names[0]]
        log_names = st.multiselect("Log Magnitude", all_names, default=reflection_names) or [all_names[0]]
        st.header("4. Markers")
        marker_count = st.number_input("Number of markers", 1, 20, len(st.session_state.markers), 1)
        marker_values = []
        for index in range(int(marker_count)):
            default = st.session_state.markers[index] if index < len(st.session_state.markers) else start + (stop-start)*(index+1)/(marker_count+1)
            default = min(max(float(default), float(start)), float(stop))
            marker_values.append(st.number_input(f"M{index+1} frequency (GHz)", float(start), float(stop), default, 0.001, format="%.6f", key=f"cmp_marker_{index}"))
        st.session_state.markers = marker_values
    f_ghz, matrices = common_comparison_data(networks, start, stop, int(points))
    datasets = [(network.name, matrix) for network, matrix in zip(networks, matrices)]
    marker_indices = [int(np.argmin(np.abs(f_ghz - value))) for value in marker_values]

    st.subheader("Uploaded files")
    for network in networks:
        st.write(f"{network.name}: S{network.nports}P, {network.f.min()/1e9:.6g} to {network.f.max()/1e9:.6g} GHz, {len(network.f)} points")

    left, right = st.columns([1.35, 1])
    with left:
        fig = smith_plot(datasets, smith_names, marker_indices)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)
    with right:
        st.subheader("Marker comparison")
        for number, index in enumerate(marker_indices, 1):
            st.markdown(f"**M{number}: {f_ghz[index]:.6f} GHz**")
            for dataset_name, matrix in datasets:
                values = []
                for name in log_names:
                    db = 20*np.log10(max(abs(trace(matrix, name)[index]), 1e-15))
                    values.append(f"{name} {db:.2f} dB")
                st.write(f"{dataset_name}: " + ", ".join(values))

    st.subheader("SnP Log Magnitude comparison")
    chart = go.Figure()
    for dataset_name, matrix in datasets:
        for name in log_names:
            values = trace(matrix, name)
            chart.add_trace(go.Scatter(x=f_ghz, y=20*np.log10(np.maximum(np.abs(values), 1e-15)), mode="lines", name=f"{dataset_name} {name}"))
    for number, value in enumerate(marker_values, 1):
        chart.add_vline(x=value, line_width=1, line_dash="dot", annotation_text=f"M{number}")
    chart.update_layout(xaxis_title="Frequency (GHz)", yaxis_title="Log Magnitude (dB)", hovermode="x unified", margin=dict(l=20, r=20, t=20, b=20))
    fixed_plotly(chart)
    st.stop()

# -------------------- Touchstone / standalone modes --------------------
uploaded = None
if mode == "Touchstone matching":
    with st.sidebar:
        uploaded = st.file_uploader("Upload S1P/S2P/S3P", type=["s1p", "s2p", "s3p"])
    if uploaded is None:
        st.info("Upload a Touchstone file or select another mode.")
        st.stop()
    try:
        network = read_touchstone(uploaded)
    except Exception as exc:
        st.error(f"Cannot read Touchstone file: {exc}")
        st.stop()
    full_f = network.f / 1e9
    full_s = network.s
    ports = network.nports
    lower, upper = float(full_f.min()), float(full_f.max())
    with st.sidebar:
        st.header("2. Frequency range")
        c1, c2 = st.columns(2)
        start = c1.number_input("Start GHz", lower, upper, lower, format="%.6f")
        stop = c2.number_input("Stop GHz", lower, upper, upper, format="%.6f")
    if start >= stop:
        st.error("Start frequency must be smaller than stop frequency.")
        st.stop()
    mask = (full_f >= start) & (full_f <= stop)
    f_ghz, original_s = full_f[mask], full_s[mask]
else:
    ports = 2
    with st.sidebar:
        st.header("2. Frequency range")
        c1, c2 = st.columns(2)
        start = c1.number_input("Start GHz", min_value=.000001, value=.1, step=.1, format="%.6f")
        stop = c2.number_input("Stop GHz", min_value=.000002, value=10.0, step=.1, format="%.6f")
        points = st.number_input("Points", 2, 10001, 1001, 1)
    if start >= stop:
        st.error("Start frequency must be smaller than stop frequency.")
        st.stop()
    f_ghz = np.linspace(start, stop, int(points))
    original_s = None
f_hz = f_ghz * 1e9
all_names = [f"S{i+1}{j+1}" for i in range(ports) for j in range(ports)]
reflection_names = [f"S{i+1}{i+1}" for i in range(ports)]
with st.sidebar:
    st.header("3. Display")
    smith_names = st.multiselect("Smith Chart", reflection_names, default=[reflection_names[0]]) or [reflection_names[0]]
    log_names = st.multiselect("Log Magnitude", all_names, default=["S11", "S21"] if ports >= 2 else ["S11"]) or [all_names[0]]
    if mode == "Touchstone matching":
        match_name = st.selectbox("Matching port", reflection_names)
        port = int(match_name[1]) - 1
    else:
        match_name, port = "S11", 0
    st.header("4. Markers")
    marker_count = st.number_input("Number of markers", 1, 20, len(st.session_state.markers), 1)
    marker_values = []
    for index in range(int(marker_count)):
        default = st.session_state.markers[index] if index < len(st.session_state.markers) else start + (stop-start)*(index+1)/(marker_count+1)
        default = min(max(float(default), float(start)), float(stop))
        marker_values.append(st.number_input(f"M{index+1} frequency (GHz)", float(start), float(stop), default, .001, format="%.6f", key=f"marker_{index}"))
    st.session_state.markers = marker_values
marker_indices = [int(np.argmin(np.abs(f_ghz-value))) for value in marker_values]

st.subheader("Matching network")
c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1])
kind = c1.selectbox("Element", TYPES)
value = c2.number_input("Value", min_value=.1, value=2.2 if kind.endswith("L") else 1.0, step=.1, format="%.1f")
units = ["nH", "uH"] if kind.endswith("L") else ["pF", "nF"]
unit = c3.selectbox("Unit", units)
if c4.button("Add element", type="primary", use_container_width=True):
    st.session_state.components.append({"kind": kind, "value": value, "unit": unit, "value_si": value*SCALE[unit]})
    st.session_state.selected_component = len(st.session_state.components)-1
    st.rerun()

if st.session_state.components:
    st.write(" -> ".join(component_name(item, i).replace("\n\n", " ") for i, item in enumerate(st.session_state.components)))
    selected = st.selectbox("Select component to edit", range(len(st.session_state.components)), format_func=lambda i: component_name(st.session_state.components[i], i).replace("\n\n", " "))
    item = st.session_state.components[selected]
    e1, e2, e3 = st.columns(3)
    edit_kind = e1.selectbox("Type", TYPES, TYPES.index(item["kind"]), key="edit_kind")
    edit_units = ["nH", "uH"] if edit_kind.endswith("L") else ["pF", "nF"]
    current_unit = item["unit"] if item["unit"] in edit_units else edit_units[0]
    edit_value = e2.number_input("Edit value", min_value=.1, value=float(item["value"]), step=.1, format="%.1f")
    edit_unit = e3.selectbox("Edit unit", edit_units, edit_units.index(current_unit))
    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("Save", type="primary", use_container_width=True):
        st.session_state.components[selected] = {"kind": edit_kind, "value": edit_value, "unit": edit_unit, "value_si": edit_value*SCALE[edit_unit]}
        st.rerun()
    if b2.button("Move left", disabled=selected == 0, use_container_width=True):
        st.session_state.components[selected-1], st.session_state.components[selected] = st.session_state.components[selected], st.session_state.components[selected-1]
        st.rerun()
    if b3.button("Move right", disabled=selected == len(st.session_state.components)-1, use_container_width=True):
        st.session_state.components[selected+1], st.session_state.components[selected] = st.session_state.components[selected], st.session_state.components[selected+1]
        st.rerun()
    if b4.button("Delete", use_container_width=True):
        st.session_state.components.pop(selected)
        st.rerun()
    if b5.button("Clear", use_container_width=True):
        st.session_state.components = []
        st.rerun()
else:
    st.info("Add at least one L/C element.")

try:
    if mode == "Standalone LC network":
        calculated_s = standalone_lc(f_hz, st.session_state.components, z0)
    else:
        calculated_s = touchstone_matching(original_s, f_hz, st.session_state.components, port, z0)
except Exception as exc:
    st.error(f"Simulation failed: {exc}")
    st.stop()

if mode == "Standalone LC network":
    datasets = [("LC Network", calculated_s)]
else:
    datasets = [("Original", original_s)]
    if st.session_state.components:
        datasets.append(("Matched", calculated_s))
left, right = st.columns([1.35, 1])
with left:
    fig = smith_plot(datasets, smith_names, marker_indices)
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)
with right:
    st.subheader("Marker values")
    for number, index in enumerate(marker_indices, 1):
        st.markdown(f"**M{number}: {f_ghz[index]:.6f} GHz**")
        for dataset_name, matrix in datasets:
            values = []
            for name in log_names:
                db = 20*np.log10(max(abs(trace(matrix, name)[index]), 1e-15))
                values.append(f"{name} {db:.2f} dB")
            st.write(f"{dataset_name}: " + ", ".join(values))

st.subheader("S-parameter Log Magnitude")
chart = go.Figure()
for dataset_name, matrix in datasets:
    for name in log_names:
        values = trace(matrix, name)
        chart.add_trace(go.Scatter(x=f_ghz, y=20*np.log10(np.maximum(np.abs(values), 1e-15)), mode="lines", name=f"{dataset_name} {name}"))
for number, value in enumerate(marker_values, 1):
    chart.add_vline(x=value, line_width=1, line_dash="dot", annotation_text=f"M{number}")
chart.update_layout(xaxis_title="Frequency (GHz)", yaxis_title="Log Magnitude (dB)", hovermode="x unified", margin=dict(l=20, r=20, t=20, b=20))
fixed_plotly(chart)
