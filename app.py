import os
import tempfile

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import skrf as rf
import streamlit as st

st.set_page_config(page_title="Smith Chart Tool", layout="wide")
TYPES = ["Series L", "Series C", "Shunt L", "Shunt C"]
SCALE = {"nH": 1e-9, "uH": 1e-6, "pF": 1e-12, "nF": 1e-9}


def init_state():
    st.session_state.setdefault("components", [])
    st.session_state.setdefault("markers", [1.0])


def read_touchstone(upload):
    suffix = os.path.splitext(upload.name)[1].lower()
    if suffix not in {".s1p", ".s2p", ".s3p", ".s4p", ".s5p"}:
        raise ValueError("Only S1P through S5P are supported.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(upload.getbuffer())
        path = tmp.name
    try:
        network = rf.Network(path)
        network.name = os.path.splitext(upload.name)[0]
    finally:
        os.unlink(path)
    return network


def trace(matrix, name):
    return matrix[:, int(name[1]) - 1, int(name[2]) - 1]


def gamma_to_z(gamma, z0):
    with np.errstate(divide="ignore", invalid="ignore"):
        return z0 * (1 + gamma) / (1 - gamma)


def s_to_z(s_matrix, z0):
    count, ports, _ = s_matrix.shape
    eye = np.eye(ports, dtype=complex)
    result = np.empty_like(s_matrix, dtype=complex)
    for k in range(count):
        result[k] = z0 * np.linalg.solve(
            (eye - s_matrix[k]).T, (eye + s_matrix[k]).T
        ).T
    return result


def z_to_s(z_matrix, z0):
    count, ports, _ = z_matrix.shape
    eye = np.eye(ports, dtype=complex)
    result = np.empty_like(z_matrix, dtype=complex)
    for k in range(count):
        result[k] = np.linalg.solve(
            (z_matrix[k] + z0 * eye).T,
            (z_matrix[k] - z0 * eye).T,
        ).T
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
                element_y = (
                    1 / (1j * w * value)
                    if item["kind"] == "Shunt L"
                    else 1j * w * value
                )
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


def interpolate_complex(source_f, values, target_f):
    return np.interp(target_f, source_f, values.real) + 1j * np.interp(
        target_f, source_f, values.imag
    )


def comparison_data(networks, start_ghz, stop_ghz, points):
    target_ghz = np.linspace(start_ghz, stop_ghz, points)
    target_hz = target_ghz * 1e9
    matrices = []
    for network in networks:
        matrix = np.empty((points, network.nports, network.nports), complex)
        for row in range(network.nports):
            for col in range(network.nports):
                matrix[:, row, col] = interpolate_complex(
                    network.f, network.s[:, row, col], target_hz
                )
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
                ax.scatter(values[index].real, values[index].imag, s=45, color=color)
                ax.annotate(
                    f"M{number}",
                    (values[index].real, values[index].imag),
                    xytext=(4, 4),
                    textcoords="offset points",
                    color=color,
                    fontsize=8,
                )
    ax.legend(fontsize=8)
    ax.set_title("Smith Chart")
    ax.grid(False)
    fig.subplots_adjust(left=0.05, right=0.97, bottom=0.05, top=0.92)
    return fig


def marker_inputs(start, stop, key_prefix):
    marker_count = st.number_input(
        "Number of markers", 1, 20, len(st.session_state.markers), 1,
        key=f"{key_prefix}_count",
    )
    values = []
    for index in range(int(marker_count)):
        if index < len(st.session_state.markers):
            default = st.session_state.markers[index]
        else:
            default = start + (stop - start) * (index + 1) / (marker_count + 1)
        default = min(max(float(default), float(start)), float(stop))
        values.append(
            st.number_input(
                f"M{index + 1} frequency (GHz)",
                float(start), float(stop), round(default, 3), 0.001,
                format="%.3f", key=f"{key_prefix}_{index}",
            )
        )
    st.session_state.markers = values
    return values


def fixed_plotly(figure):
    figure.update_xaxes(fixedrange=True)
    figure.update_yaxes(fixedrange=True)
    st.plotly_chart(
        figure,
        use_container_width=True,
        config={
            "scrollZoom": False,
            "displaylogo": False,
            "modeBarButtonsToRemove": [
                "zoom2d", "pan2d", "select2d", "lasso2d",
                "zoomIn2d", "zoomOut2d", "autoScale2d",
            ],
        },
    )


def marker_comparison_tables(datasets, parameters, f_ghz, marker_indices):
    st.subheader("Marker comparison tables")
    st.caption("Rows are SnP files and columns are marker frequencies. Values are Log Magnitude in dB.")
    marker_columns = [
        f"M{number} @ {f_ghz[index]:.3f} GHz"
        for number, index in enumerate(marker_indices, 1)
    ]
    for parameter in parameters:
        rows = {}
        for dataset_name, matrix in datasets:
            rows[dataset_name] = [
                20 * np.log10(max(abs(trace(matrix, parameter)[index]), 1e-15))
                for index in marker_indices
            ]
        table = pd.DataFrame.from_dict(rows, orient="index", columns=marker_columns)
        table.index.name = "SnP file"
        with st.expander(f"{parameter} comparison", expanded=True):
            st.dataframe(table.style.format("{:.2f} dB"), use_container_width=True)
            if parameter[1] == parameter[2]:
                st.caption("Reflection parameter: a more negative dB value normally means better matching.")
            else:
                st.caption("Transmission parameter: a value closer to 0 dB normally means lower loss.")


def component_editor():
    c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1])
    kind = c1.selectbox("Element", TYPES)
    value = c2.number_input(
        "Value", min_value=0.1,
        value=2.2 if kind.endswith("L") else 1.0,
        step=0.1, format="%.1f",
    )
    units = ["nH", "uH"] if kind.endswith("L") else ["pF", "nF"]
    unit = c3.selectbox("Unit", units)
    if c4.button("Add element", type="primary", use_container_width=True):
        st.session_state.components.append(
            {"kind": kind, "value": value, "unit": unit, "value_si": value * SCALE[unit]}
        )
        st.rerun()

    if not st.session_state.components:
        st.info("Add at least one L/C element.")
        return

    st.write(
        " -> ".join(
            f"{index + 1}. {item['kind']} {item['value']:g} {item['unit']}"
            for index, item in enumerate(st.session_state.components)
        )
    )
    selected = st.selectbox(
        "Select component to edit",
        range(len(st.session_state.components)),
        format_func=lambda index: (
            f"{index + 1}. {st.session_state.components[index]['kind']} "
            f"{st.session_state.components[index]['value']:g} "
            f"{st.session_state.components[index]['unit']}"
        ),
    )
    item = st.session_state.components[selected]
    e1, e2, e3 = st.columns(3)
    edit_kind = e1.selectbox("Type", TYPES, TYPES.index(item["kind"]), key="edit_kind")
    edit_units = ["nH", "uH"] if edit_kind.endswith("L") else ["pF", "nF"]
    current_unit = item["unit"] if item["unit"] in edit_units else edit_units[0]
    edit_value = e2.number_input(
        "Edit value", min_value=0.1, value=float(item["value"]),
        step=0.1, format="%.1f",
    )
    edit_unit = e3.selectbox("Edit unit", edit_units, edit_units.index(current_unit))
    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("Save", type="primary", use_container_width=True):
        st.session_state.components[selected] = {
            "kind": edit_kind,
            "value": edit_value,
            "unit": edit_unit,
            "value_si": edit_value * SCALE[edit_unit],
        }
        st.rerun()
    if b2.button("Move left", disabled=selected == 0, use_container_width=True):
        items = st.session_state.components
        items[selected - 1], items[selected] = items[selected], items[selected - 1]
        st.rerun()
    if b3.button(
        "Move right",
        disabled=selected == len(st.session_state.components) - 1,
        use_container_width=True,
    ):
        items = st.session_state.components
        items[selected + 1], items[selected] = items[selected], items[selected + 1]
        st.rerun()
    if b4.button("Delete", use_container_width=True):
        st.session_state.components.pop(selected)
        st.rerun()
    if b5.button("Clear", use_container_width=True):
        st.session_state.components = []
        st.rerun()


init_state()
st.title("Streamlit Smith Chart Tool")
st.caption("Version 9.4 - S5P support and 3-decimal markers")

with st.sidebar:
    st.header("1. Simulation source")
    mode = st.radio(
        "Mode",
        ["Touchstone matching", "Standalone LC network", "SnP file comparison"],
    )
    z0 = st.number_input("Z0 (ohm)", 1.0, 1000.0, 50.0, 1.0)

if mode == "SnP file comparison":
    with st.sidebar:
        uploads = st.file_uploader(
            "Upload 2 or 3 SnP files",
            type=["s1p", "s2p", "s3p", "s4p", "s5p"],
            accept_multiple_files=True,
        )
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
    if len({network.nports for network in networks}) != 1:
        st.error("All comparison files must have the same port count.")
        st.stop()

    ports = networks[0].nports
    overlap_start = max(network.f.min() for network in networks) / 1e9
    overlap_stop = min(network.f.max() for network in networks) / 1e9
    if overlap_start >= overlap_stop:
        st.error("The files do not have an overlapping frequency range.")
        st.stop()

    all_names = [f"S{i+1}{j+1}" for i in range(ports) for j in range(ports)]
    reflection_names = [f"S{i+1}{i+1}" for i in range(ports)]
    with st.sidebar:
        st.header("2. Comparison range")
        c1, c2 = st.columns(2)
        start = c1.number_input(
            "Start GHz", overlap_start, overlap_stop, overlap_start, format="%.6f"
        )
        stop = c2.number_input(
            "Stop GHz", overlap_start, overlap_stop, overlap_stop, format="%.6f"
        )
        points = st.number_input("Interpolation points", 2, 10001, 1001, 1)
        if start >= stop:
            st.error("Start frequency must be smaller than stop frequency.")
            st.stop()
        st.header("3. Comparison traces")
        smith_names = st.multiselect(
            "Smith Chart", reflection_names, default=[reflection_names[0]]
        ) or [reflection_names[0]]
        log_names = st.multiselect(
            "Log Magnitude and marker tables", all_names, default=reflection_names
        ) or [all_names[0]]
        st.header("4. Markers")
        marker_values = marker_inputs(start, stop, "comparison_marker")

    f_ghz, matrices = comparison_data(networks, start, stop, int(points))
    datasets = [(network.name, matrix) for network, matrix in zip(networks, matrices)]
    marker_indices = [int(np.argmin(np.abs(f_ghz - value))) for value in marker_values]

    st.subheader("Uploaded files")
    file_table = pd.DataFrame(
        [
            {
                "File": network.name,
                "Type": f"S{network.nports}P",
                "Start (GHz)": network.f.min() / 1e9,
                "Stop (GHz)": network.f.max() / 1e9,
                "Points": len(network.f),
            }
            for network in networks
        ]
    )
    st.dataframe(file_table, use_container_width=True, hide_index=True)

    st.subheader("Smith Chart comparison")
    smith_left, smith_center, smith_right = st.columns([0.20, 0.60, 0.20])
    with smith_center:
        fig = smith_plot(datasets, smith_names, marker_indices)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

    st.subheader("SnP Log Magnitude comparison")
    chart_column, table_column = st.columns([1.55, 1.0], gap="large")
    chart = go.Figure()
    for dataset_name, matrix in datasets:
        for name in log_names:
            values = trace(matrix, name)
            chart.add_trace(
                go.Scatter(
                    x=f_ghz,
                    y=20 * np.log10(np.maximum(np.abs(values), 1e-15)),
                    mode="lines",
                    name=f"{dataset_name} {name}",
                )
            )
    for number, value in enumerate(marker_values, 1):
        chart.add_vline(
            x=value, line_width=1, line_dash="dot", annotation_text=f"M{number}"
        )
    chart.update_layout(
        xaxis_title="Frequency (GHz)",
        yaxis_title="Log Magnitude (dB)",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=20, b=105),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.24,
            xanchor="left",
            x=0,
            title_text="",
        ),
    )
    with chart_column:
        fixed_plotly(chart)
    with table_column:
        marker_comparison_tables(datasets, log_names, f_ghz, marker_indices)
    st.stop()

# Touchstone matching and standalone LC modes
if mode == "Touchstone matching":
    with st.sidebar:
        uploaded = st.file_uploader("Upload S1P-S5P", type=["s1p", "s2p", "s3p", "s4p", "s5p"])
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
        start = c1.number_input("Start GHz", min_value=0.000001, value=0.1, step=0.1)
        stop = c2.number_input("Stop GHz", min_value=0.000002, value=10.0, step=0.1)
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
    smith_names = st.multiselect(
        "Smith Chart", reflection_names, default=[reflection_names[0]]
    ) or [reflection_names[0]]
    log_names = st.multiselect(
        "Log Magnitude", all_names,
        default=["S11", "S21"] if ports >= 2 else ["S11"],
    ) or [all_names[0]]
    if mode == "Touchstone matching":
        match_name = st.selectbox("Matching port", reflection_names)
        port = int(match_name[1]) - 1
    else:
        port = 0
    st.header("4. Markers")
    marker_values = marker_inputs(start, stop, "simulation_marker")
marker_indices = [int(np.argmin(np.abs(f_ghz - value))) for value in marker_values]

st.subheader("Matching network")
component_editor()

try:
    if mode == "Standalone LC network":
        calculated_s = standalone_lc(f_hz, st.session_state.components, z0)
        datasets = [("LC Network", calculated_s)]
    else:
        calculated_s = touchstone_matching(
            original_s, f_hz, st.session_state.components, port, z0
        )
        datasets = [("Original", original_s)]
        if st.session_state.components:
            datasets.append(("Matched", calculated_s))
except Exception as exc:
    st.error(f"Simulation failed: {exc}")
    st.stop()

left, right = st.columns([1.35, 1])
with left:
    inner_left, inner_chart, inner_right = st.columns([0.20, 0.60, 0.20])
    with inner_chart:
        fig = smith_plot(datasets, smith_names, marker_indices)
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)
with right:
    marker_comparison_tables(datasets, log_names, f_ghz, marker_indices)

st.subheader("S-parameter Log Magnitude")
chart = go.Figure()
for dataset_name, matrix in datasets:
    for name in log_names:
        values = trace(matrix, name)
        chart.add_trace(
            go.Scatter(
                x=f_ghz,
                y=20 * np.log10(np.maximum(np.abs(values), 1e-15)),
                mode="lines",
                name=f"{dataset_name} {name}",
            )
        )
for number, value in enumerate(marker_values, 1):
    chart.add_vline(x=value, line_width=1, line_dash="dot", annotation_text=f"M{number}")
chart.update_layout(
    xaxis_title="Frequency (GHz)",
    yaxis_title="Log Magnitude (dB)",
    hovermode="x unified",
    margin=dict(l=20, r=20, t=20, b=20),
)
fixed_plotly(chart)
