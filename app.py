import os
import tempfile

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import skrf as rf
import streamlit as st

st.set_page_config(page_title="Streamlit Smith Chart Tool", page_icon="RF", layout="wide")
Z0_DEFAULT = 50.0
COMPONENT_TYPES = ["Series L", "Series C", "Shunt L", "Shunt C"]
SCALE = {"pF": 1e-12, "nF": 1e-9, "nH": 1e-9, "uH": 1e-6}


def init_state():
    st.session_state.setdefault("components", [])
    st.session_state.setdefault("selected_component", None)


def read_touchstone(uploaded_file):
    suffix = os.path.splitext(uploaded_file.name)[1].lower()
    if suffix not in {".s1p", ".s2p", ".s3p"}:
        raise ValueError("Only .s1p, .s2p, and .s3p files are supported.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        path = tmp.name
    try:
        network = rf.Network(path)
    finally:
        os.unlink(path)
    if network.nports > 3:
        raise ValueError("This version supports up to 3 ports.")
    return network


def gamma_to_z(gamma, z0):
    with np.errstate(divide="ignore", invalid="ignore"):
        return z0 * (1.0 + gamma) / (1.0 - gamma)


def electrical_metrics(gamma):
    mag = np.abs(gamma)
    safe = np.maximum(mag, 1e-15)
    s_db = 20.0 * np.log10(safe)
    return_loss = -s_db
    vswr = np.where(mag < 1.0, (1.0 + mag) / np.maximum(1.0 - mag, 1e-15), np.inf)
    return s_db, return_loss, vswr


def s_to_z_matrix(s_matrix, z0):
    nfreq, nports, _ = s_matrix.shape
    identity = np.eye(nports, dtype=complex)
    result = np.empty_like(s_matrix, dtype=complex)
    for k in range(nfreq):
        result[k] = z0 * np.linalg.solve(
            (identity - s_matrix[k]).T, (identity + s_matrix[k]).T
        ).T
    return result


def z_to_s_matrix(z_matrix, z0):
    nfreq, nports, _ = z_matrix.shape
    identity = np.eye(nports, dtype=complex)
    result = np.empty_like(z_matrix, dtype=complex)
    for k in range(nfreq):
        numerator = z_matrix[k] - z0 * identity
        denominator = z_matrix[k] + z0 * identity
        result[k] = np.linalg.solve(denominator.T, numerator.T).T
    return result


def apply_matching_multiport(s_matrix, frequency_hz, components, port, z0):
    z_matrix = s_to_z_matrix(np.asarray(s_matrix, dtype=complex), z0)
    omega = 2.0 * np.pi * np.asarray(frequency_hz, dtype=float)
    for item in components:
        kind = item["kind"]
        value = float(item["value_si"])
        if kind == "Series L":
            z_matrix[:, port, port] += 1j * omega * value
        elif kind == "Series C":
            with np.errstate(divide="ignore", invalid="ignore"):
                z_matrix[:, port, port] += 1.0 / (1j * omega * value)
        else:
            for k, w in enumerate(omega):
                y_matrix = np.linalg.inv(z_matrix[k])
                if kind == "Shunt L":
                    element_y = 1.0 / (1j * w * value)
                else:
                    element_y = 1j * w * value
                y_matrix[port, port] += element_y
                z_matrix[k] = np.linalg.inv(y_matrix)
    return z_to_s_matrix(z_matrix, z0)


def standalone_lc_s(frequency_hz, components, z0):
    """Calculate the 2-port S matrix of an ideal LC ladder using ABCD matrices."""
    omega = 2.0 * np.pi * np.asarray(frequency_hz, dtype=float)
    result = np.zeros((len(omega), 2, 2), dtype=complex)
    for k, w in enumerate(omega):
        total = np.eye(2, dtype=complex)
        for item in components:
            kind = item["kind"]
            value = float(item["value_si"])
            if kind == "Series L":
                element = np.array([[1, 1j * w * value], [0, 1]], dtype=complex)
            elif kind == "Series C":
                element = np.array([[1, 1 / (1j * w * value)], [0, 1]], dtype=complex)
            elif kind == "Shunt L":
                element = np.array([[1, 0], [1 / (1j * w * value), 1]], dtype=complex)
            else:
                element = np.array([[1, 0], [1j * w * value, 1]], dtype=complex)
            total = total @ element
        a, b, cc, d = total[0, 0], total[0, 1], total[1, 0], total[1, 1]
        denominator = a + b / z0 + cc * z0 + d
        result[k, 0, 0] = (a + b / z0 - cc * z0 - d) / denominator
        result[k, 1, 0] = 2 / denominator
        result[k, 0, 1] = 2 * (a * d - b * cc) / denominator
        result[k, 1, 1] = (-a + b / z0 - cc * z0 + d) / denominator
    return result


def ideal_thru_s(point_count):
    result = np.zeros((point_count, 2, 2), dtype=complex)
    result[:, 1, 0] = 1.0
    result[:, 0, 1] = 1.0
    return result


def extract_traces(s_matrix, names):
    traces = {}
    for name in names:
        row = int(name[1]) - 1
        col = int(name[2]) - 1
        traces[name] = s_matrix[:, row, col]
    return traces


def smith_figure(original_traces, matched_traces, marker_index, standalone=False):
    fig, ax = plt.subplots(figsize=(8, 8))
    rf.plotting.smith(smithR=1, chart_type="z", draw_labels=False, ax=ax)
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for index, (name, gamma) in enumerate(original_traces.items()):
        color = colors[index % len(colors)]
        ax.plot(gamma.real, gamma.imag, lw=2, color=color, label=name if standalone else f"Original {name}")
        ax.scatter(gamma[marker_index].real, gamma[marker_index].imag, s=40, color=color, zorder=5)
        if name in matched_traces:
            matched = matched_traces[name]
            ax.plot(matched.real, matched.imag, lw=2, ls="--", color=color, label=f"Matched {name}")
            ax.scatter(matched[marker_index].real, matched[marker_index].imag, s=55, marker="X", color=color, zorder=6)
    ax.set_title("Smith Chart")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(False)
    fig.subplots_adjust(left=0.06, right=0.96, bottom=0.06, top=0.92)
    return fig


def component_label(item, index):
    name = {"Series L": "L", "Series C": "C", "Shunt L": "L to GND", "Shunt C": "C to GND"}[item["kind"]]
    return f"{index + 1}. {name}\n\n{item['display_value']:g} {item['unit']}"


init_state()
st.title("Streamlit Smith Chart Tool")
st.caption("Version 8.1 - Standalone LC results without Original traces")
st.caption("Upload S1P, S2P, or S3P data, apply an ideal L/C network, and inspect multiport results.")

with st.sidebar:
    st.header("1. Simulation source")
    simulation_mode = st.radio(
        "Mode",
        ["Touchstone file", "Standalone LC network"],
        help="Standalone mode simulates the LC ladder between two equal reference impedances without an SNP file.",
    )
    uploaded = None
    if simulation_mode == "Touchstone file":
        uploaded = st.file_uploader("Upload file", type=["s1p", "s2p", "s3p"])
    else:
        st.info("Standalone mode: Port 1 -> LC ladder -> Port 2")
    st.header("2. Reference impedance")
    z0 = st.number_input("Z0 (ohm)", min_value=1.0, max_value=1000.0, value=Z0_DEFAULT, step=1.0)

if simulation_mode == "Touchstone file" and uploaded is None:
    st.info("Upload a .s1p, .s2p, or .s3p file, or select Standalone LC network in the sidebar.")
    st.stop()

if simulation_mode == "Touchstone file":
    try:
        ntwk = read_touchstone(uploaded)
    except Exception as exc:
        st.error(f"Unable to read Touchstone file: {exc}")
        st.stop()

    full_freq_hz = np.asarray(ntwk.f, dtype=float)
    full_freq_ghz = full_freq_hz / 1e9
    full_s = np.asarray(ntwk.s)
    nports = ntwk.nports
    with st.sidebar:
        st.success(f"Loaded {uploaded.name}: {nports}-port, {len(full_freq_hz)} points")
        st.header("3. Simulation frequency range")
        file_start = float(full_freq_ghz.min())
        file_stop = float(full_freq_ghz.max())
        frequency_step = max((file_stop - file_start) / max(len(full_freq_ghz) - 1, 1), 1e-6)
        range_col1, range_col2 = st.columns(2)
        start_ghz = range_col1.number_input("Start (GHz)", min_value=file_start, max_value=file_stop, value=file_start, step=frequency_step, format="%.6f")
        stop_ghz = range_col2.number_input("Stop (GHz)", min_value=file_start, max_value=file_stop, value=file_stop, step=frequency_step, format="%.6f")
    if start_ghz >= stop_ghz:
        st.error("Start frequency must be lower than stop frequency.")
        st.stop()
    frequency_mask = (full_freq_ghz >= start_ghz) & (full_freq_ghz <= stop_ghz)
    if np.count_nonzero(frequency_mask) < 2:
        st.error("The selected range contains fewer than two Touchstone frequency points.")
        st.stop()
    freq_hz = full_freq_hz[frequency_mask]
    freq_ghz = full_freq_ghz[frequency_mask]
    s = full_s[frequency_mask]
else:
    nports = 2
    with st.sidebar:
        st.header("3. Simulation frequency range")
        range_col1, range_col2 = st.columns(2)
        start_ghz = range_col1.number_input("Start (GHz)", min_value=0.000001, value=0.1, step=0.1, format="%.6f")
        stop_ghz = range_col2.number_input("Stop (GHz)", min_value=0.000002, value=10.0, step=0.1, format="%.6f")
        point_count = st.number_input("Frequency points", min_value=2, max_value=10001, value=1001, step=1)
    if start_ghz >= stop_ghz:
        st.error("Start frequency must be lower than stop frequency.")
        st.stop()
    freq_ghz = np.linspace(start_ghz, stop_ghz, int(point_count))
    freq_hz = freq_ghz * 1e9
    s = ideal_thru_s(len(freq_hz))

choices = [f"S{i+1}{j+1}" for i in range(nports) for j in range(nports)]
reflection_choices = [f"S{i+1}{i+1}" for i in range(nports)]

with st.sidebar:
    st.caption(f"Active range: {freq_ghz.min():.6g} to {freq_ghz.max():.6g} GHz, {len(freq_hz)} points")
    st.header("4. Independent display selections")
    st.info("V7.2: Smith Chart and Log Magnitude use separate selections.")
    smith_parameters = st.multiselect(
        "4A. Smith Chart S-parameters",
        reflection_choices,
        default=[reflection_choices[0]],
        help="Normally select reflection parameters such as S11, S22, or S33.",
    )
    if not smith_parameters:
        smith_parameters = [reflection_choices[0]]
        st.warning(f"Smith Chart defaults to {reflection_choices[0]}.")

    log_parameters = st.multiselect(
        "4B. Log Magnitude S-parameters",
        choices,
        default=reflection_choices,
        help="Select any combination, such as S21 + S11 or S21 + S22.",
    )
    if not log_parameters:
        log_parameters = [choices[0]]
        st.warning(f"Log Magnitude defaults to {choices[0]}.")

    if simulation_mode == "Touchstone file":
        selected_reflection = st.selectbox(
            "4C. Port for matching simulation",
            reflection_choices,
            help="This selects the physical port where the L/C network is placed.",
        )
        port = int(selected_reflection[1]) - 1
    else:
        selected_reflection = "S11"
        port = 0
        st.caption("Standalone topology: Port 1 -> LC ladder -> Port 2")
    step = max(float((freq_ghz.max() - freq_ghz.min()) / max(len(freq_ghz) - 1, 1)), 1e-6)
    target_ghz = st.slider(
        "Marker frequency (GHz)",
        min_value=float(freq_ghz.min()),
        max_value=float(freq_ghz.max()),
        value=float(freq_ghz[len(freq_ghz) // 2]),
        step=step,
    )

marker_idx = int(np.argmin(np.abs(freq_ghz - target_ghz)))
reflection_gamma = s[:, port, port]
input_z = gamma_to_z(reflection_gamma, z0)

st.subheader("Matching network")
if simulation_mode == "Touchstone file":
    st.info("The L/C network is connected to the selected physical port. The complete S matrix is recalculated.")
else:
    st.info("Standalone mode simulates the component chain from Port 1 to Port 2 with no SNP file.")
a, b, c1, d = st.columns([1.3, 1, 1, 1])
with a:
    kind = st.selectbox("Element", COMPONENT_TYPES)
with b:
    value = st.number_input("Value", min_value=0.0001, value=2.2 if "L" in kind else 1.0, format="%.4f")
with c1:
    units = ["nH", "uH"] if "L" in kind else ["pF", "nF"]
    unit = st.selectbox("Unit", units)
with d:
    st.write("")
    st.write("")
    add = st.button("Add element", type="primary", use_container_width=True)
if add:
    st.session_state.components.append({"kind": kind, "display_value": value, "unit": unit, "value_si": value * SCALE[unit]})
    st.session_state.selected_component = len(st.session_state.components) - 1
    st.rerun()

st.markdown("#### Matching network placement")
if st.session_state.components:
    widths = [1.0] + sum(([0.25, 1.2] for _ in st.session_state.components), []) + [0.25, 1.0]
    cols = st.columns(widths)
    cols[0].markdown("<div style='text-align:center;padding-top:18px'><b>DUT</b></div>", unsafe_allow_html=True)
    pos = 1
    for index, item in enumerate(st.session_state.components):
        cols[pos].markdown("<div style='text-align:center;padding-top:18px'>→</div>", unsafe_allow_html=True)
        pos += 1
        if cols[pos].button(
            ("✓ " if st.session_state.selected_component == index else "") + component_label(item, index),
            key=f"select_{index}", use_container_width=True,
            type="primary" if st.session_state.selected_component == index else "secondary",
        ):
            st.session_state.selected_component = index
            st.rerun()
        pos += 1
    cols[pos].markdown("<div style='text-align:center;padding-top:18px'>→</div>", unsafe_allow_html=True)
    cols[pos + 1].markdown(f"<div style='text-align:center;padding-top:18px'><b>{'Port 2' if simulation_mode == 'Standalone LC network' else f'Port {port + 1}'}</b><br>{z0:g} ohm</div>", unsafe_allow_html=True)

    index = st.session_state.selected_component
    if index is not None and index < len(st.session_state.components):
        item = st.session_state.components[index]
        st.markdown(f"#### Edit component {index + 1}")
        edit_kind = st.selectbox("Component type", COMPONENT_TYPES, index=COMPONENT_TYPES.index(item["kind"]), key=f"ek_{index}")
        edit_units = ["nH", "uH"] if "L" in edit_kind else ["pF", "nF"]
        current_unit = item["unit"] if item["unit"] in edit_units else edit_units[0]
        e1, e2 = st.columns(2)
        edit_value = e1.number_input("Component value", min_value=0.0001, value=float(item["display_value"]), format="%.4f", key=f"ev_{index}")
        edit_unit = e2.selectbox("Component unit", edit_units, index=edit_units.index(current_unit), key=f"eu_{index}_{edit_kind}")
        x1, x2, x3, x4 = st.columns(4)
        if x1.button("Save changes", type="primary", use_container_width=True):
            st.session_state.components[index] = {"kind": edit_kind, "display_value": edit_value, "unit": edit_unit, "value_si": edit_value * SCALE[edit_unit]}
            st.rerun()
        if x2.button("Move left", disabled=index == 0, use_container_width=True):
            st.session_state.components[index - 1], st.session_state.components[index] = st.session_state.components[index], st.session_state.components[index - 1]
            st.session_state.selected_component = index - 1
            st.rerun()
        if x3.button("Move right", disabled=index == len(st.session_state.components) - 1, use_container_width=True):
            st.session_state.components[index + 1], st.session_state.components[index] = st.session_state.components[index], st.session_state.components[index + 1]
            st.session_state.selected_component = index + 1
            st.rerun()
        if x4.button("Delete", use_container_width=True):
            st.session_state.components.pop(index)
            st.session_state.selected_component = min(index, len(st.session_state.components) - 1) if st.session_state.components else None
            st.rerun()
    if st.button("Clear network"):
        st.session_state.components = []
        st.session_state.selected_component = None
        st.rerun()
else:
    st.info("No matching elements have been added.")

try:
    if simulation_mode == "Standalone LC network":
        matched_s = standalone_lc_s(freq_hz, st.session_state.components, z0)
    else:
        matched_s = apply_matching_multiport(s, freq_hz, st.session_state.components, port, z0)
except (np.linalg.LinAlgError, ZeroDivisionError, FloatingPointError) as exc:
    st.error(f"Simulation calculation failed: {exc}")
    st.stop()

matched_gamma = matched_s[:, port, port]
matched_z = gamma_to_z(matched_gamma, z0)
s_db_before, rl_before, vswr_before = electrical_metrics(reflection_gamma)
s_db_after, rl_after, vswr_after = electrical_metrics(matched_gamma)

if simulation_mode == "Standalone LC network":
    # Standalone mode represents a network created from scratch, so only its
    # calculated results are displayed. There is no Original/Matched comparison.
    smith_original = extract_traces(matched_s, smith_parameters)
    smith_matched = {}
    log_original = extract_traces(matched_s, log_parameters)
    log_matched = {}
else:
    smith_original = extract_traces(s, smith_parameters)
    smith_matched = extract_traces(matched_s, smith_parameters) if st.session_state.components else {}
    log_original = extract_traces(s, log_parameters)
    log_matched = extract_traces(matched_s, log_parameters) if st.session_state.components else {}

left, right = st.columns([1.35, 1])
with left:
    st.subheader("Smith Chart")
    st.caption("Selection is independent from the Log Magnitude chart. Reflection parameters are recommended.")
    fig = smith_figure(smith_original, smith_matched, marker_idx, simulation_mode == "Standalone LC network")
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)
with right:
    st.subheader(f"Marker at {freq_ghz[marker_idx]:.6g} GHz")
    if simulation_mode == "Standalone LC network":
        st.write(f"**Input Z:** {matched_z[marker_idx].real:.3f} {'+' if matched_z[marker_idx].imag >= 0 else '-'} j{abs(matched_z[marker_idx].imag):.3f} ohm")
        st.write(f"**S11:** {s_db_after[marker_idx]:.2f} dB, VSWR {vswr_after[marker_idx]:.3f}")
    else:
        st.write(f"**Original Z at Port {port + 1}:** {input_z[marker_idx].real:.3f} {'+' if input_z[marker_idx].imag >= 0 else '-'} j{abs(input_z[marker_idx].imag):.3f} ohm")
        st.write(f"**Matched Z at Port {port + 1}:** {matched_z[marker_idx].real:.3f} {'+' if matched_z[marker_idx].imag >= 0 else '-'} j{abs(matched_z[marker_idx].imag):.3f} ohm")
        st.write(f"**Original {selected_reflection}:** {s_db_before[marker_idx]:.2f} dB, VSWR {vswr_before[marker_idx]:.3f}")
        st.write(f"**Matched {selected_reflection}:** {s_db_after[marker_idx]:.2f} dB, VSWR {vswr_after[marker_idx]:.3f}")
    st.markdown("**Log Magnitude selections at marker:**")
    for name, trace in log_original.items():
        value_db = 20 * np.log10(max(abs(trace[marker_idx]), 1e-15))
        if simulation_mode == "Standalone LC network":
            text = f"{name}: {value_db:.2f} dB"
        else:
            text = f"Original {name}: {value_db:.2f} dB"
            if name in log_matched:
                matched_db = 20 * np.log10(max(abs(log_matched[name][marker_idx]), 1e-15))
                text += f" | Matched {name}: {matched_db:.2f} dB"
        st.write(text)

st.subheader("S-parameter Log Magnitude")
st.caption("This plot uses its own independent parameter selection from the sidebar.")
response = {"Frequency (GHz)": freq_ghz}
for name, trace in log_original.items():
    if simulation_mode == "Standalone LC network":
        response[f"{name} (dB)"] = 20 * np.log10(np.maximum(np.abs(trace), 1e-15))
    else:
        response[f"Original {name} (dB)"] = 20 * np.log10(np.maximum(np.abs(trace), 1e-15))
        if name in log_matched:
            response[f"Matched {name} (dB)"] = 20 * np.log10(np.maximum(np.abs(log_matched[name]), 1e-15))
response_df = pd.DataFrame(response)
log_figure = go.Figure()
for column in response_df.columns:
    if column == "Frequency (GHz)":
        continue
    log_figure.add_trace(
        go.Scatter(
            x=response_df["Frequency (GHz)"],
            y=response_df[column],
            mode="lines",
            name=column,
            hovertemplate="Frequency: %{x:.6g} GHz<br>Magnitude: %{y:.2f} dB<extra>%{fullData.name}</extra>",
        )
    )
log_figure.update_layout(
    xaxis_title="Frequency (GHz)",
    yaxis_title="Log Magnitude (dB)",
    hovermode="x unified",
    margin=dict(l=20, r=20, t=20, b=20),
    legend=dict(orientation="h", yanchor="top", y=-0.22, xanchor="left", x=0),
)
log_figure.update_xaxes(range=[float(freq_ghz.min()), float(freq_ghz.max())], fixedrange=True)
log_figure.update_yaxes(fixedrange=True)
st.plotly_chart(
    log_figure,
    use_container_width=True,
    config={
        "scrollZoom": False,
        "displaylogo": False,
        "modeBarButtonsToRemove": ["zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d", "autoScale2d"],
    },
)

st.subheader("Data and export")
export_df = pd.DataFrame({"frequency_hz": freq_hz, "frequency_ghz": freq_ghz})
for name in sorted(set(smith_parameters + log_parameters)):
    matched = extract_traces(matched_s, [name])[name]
    if simulation_mode == "Standalone LC network":
        export_df[f"{name.lower()}_real"] = matched.real
        export_df[f"{name.lower()}_imag"] = matched.imag
        export_df[f"{name.lower()}_db"] = 20 * np.log10(np.maximum(np.abs(matched), 1e-15))
    else:
        original = extract_traces(s, [name])[name]
        export_df[f"original_{name.lower()}_real"] = original.real
        export_df[f"original_{name.lower()}_imag"] = original.imag
        export_df[f"original_{name.lower()}_db"] = 20 * np.log10(np.maximum(np.abs(original), 1e-15))
        export_df[f"matched_{name.lower()}_real"] = matched.real
        export_df[f"matched_{name.lower()}_imag"] = matched.imag
        export_df[f"matched_{name.lower()}_db"] = 20 * np.log10(np.maximum(np.abs(matched), 1e-15))
st.dataframe(export_df, use_container_width=True, height=320)
st.download_button("Download result CSV", export_df.to_csv(index=False).encode("utf-8"), "smith_matching_result.csv", "text/csv")

with st.expander("Model assumptions"):
    st.markdown("""
- Smith Chart and Log Magnitude selections are independent.
- Calculations and exports use only the selected start-to-stop frequency range.
- The Log Magnitude axes are fixed, so mouse-wheel scrolling does not zoom the plot.
- Touchstone mode embeds the ideal L/C network at the selected port and recalculates the complete multiport S matrix.
- Standalone mode calculates the LC ladder as an ideal 2-port network between Port 1 and Port 2 using ABCD matrices.
- Components are ideal. ESR, Q, SRF, package parasitics, transmission lines, vias, and layout coupling are not included.
- All ports use the entered equal, real reference impedance, normally 50 ohms.
""")
