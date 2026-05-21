"""
Quick end-to-end test: download real NOAA SST data,
run the filter pipeline, and produce a static phase diagram.
"""
from el_nino.pipeline import run_sst, load_output
from el_nino.plots import plot_phase_diagram, plot_timeseries
import matplotlib
matplotlib.use('Agg')

print("=== Running SST pipeline ===")
result = run_sst(
    local_file="data/input/sst1950_1981.txt",
    ano_inicio=1975,
    HN1=10.0,
    HN2=9.0,
    NDOTS=5,
    output_file="data/output/sst_test.dat",
)

print(f"\nSIGMA30 = {result['sigma30']:.4f}")
print(f"SIGMA04 = {result['sigma04']:.4f}")
print(f"NT      = {len(result['SST0'])}")

print("\n=== Loading output and plotting ===")
data = load_output("data/output/sst_test.dat")

fig = plot_phase_diagram(
    data=data,
    title="El Niño SST Phase Diagram 1975-present",
    xlabel="Temperature (°C)",
    xlim=[17.5, 32.5],
    ylim=[-2.5, 2.5],
    save_path="data/output/sst_phase_diagram.png",
)
print("Phase diagram saved: data/output/sst_phase_diagram.png")

fig2 = plot_timeseries(
    data=data,
    title="SST NINO1+2 filtered",
    ylabel="Temperature (°C)",
    save_path="data/output/sst_timeseries.png",
)
print("Time series saved: data/output/sst_timeseries.png")
