import json
from pathlib import Path
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "outputs"
p = json.loads((ROOT / "extension/parameters.json").read_text())
base = out / "protocols_final"
fig, axes = plt.subplots(1, 3, figsize=(14, 4), layout="constrained")
for ax, test, title in zip(
    axes,
    ["T1", "T2", "T3"],
    ["T1  Symmetric compression", "T2  Cylinder drape", "T3  One-sided pull"],
):
    data = np.load(base / f"{test}.npz")
    x = data["final"]
    ax.axhline(0, color="#64748b", lw=1)
    if test != "T1":
        ax.add_patch(Circle((0, 0.12), 0.12, color="#cbd5e1"))
    ax.plot(
        x[:, 0],
        x[:, 1],
        color="#0f766e",
        lw=2,
        label="CUDA, friction 0.35" if test == "T3" else "CUDA",
    )
    if test == "T3":
        control = np.load(base / "T3_mu0.npz")["final"]
        ax.plot(
            control[:, 0],
            control[:, 1],
            color="#f97316",
            ls="--",
            lw=1.5,
            label="Friction 0 control",
        )
        ax.legend(loc="upper right", fontsize=8)
    ax.set(
        xlim=(-0.53, 0.63),
        ylim=(-0.015, 0.32),
        aspect="equal",
        xlabel="x (m)",
        ylabel="height (m)",
        title=title,
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.15)
fig.savefig(out / "three_tests.png", dpi=180)
plt.close(fig)
rows = [json.loads(l) for l in (out / "real_final/stats.jsonl").read_text().splitlines()]
frame = [r["frame"] for r in rows]
fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
axes[0, 0].plot(frame, [100 * r["max_length_error"] for r in rows], label="maximum")
axes[0, 0].plot(frame, [100 * r["p99_length_error"] for r in rows], label="p99")
axes[0, 0].axhline(2, color="red", ls="--", label="max limit 2%")
axes[0, 0].set(title="Real hair: relative length error", ylabel="%")
axes[0, 0].legend(fontsize=8)
axes[0, 1].plot(frame, [-1e6 * min(r["min_gap"], 0) for r in rows])
axes[0, 1].axhline(0.25 * p["guide_radius"] * 1e6, color="red", ls="--")
axes[0, 1].set(title="Real hair: mesh surface penetration", ylabel="micrometers")
axes[1, 0].plot(frame, [r["native_ms"] for r in rows])
axes[1, 0].set(title="Exported input: native CUDA time", ylabel="ms", xlabel="frame")
off = np.load(out / "input/offsets.npy")
t = np.load(out / "input/targets.npy", mmap_mode="r")
delta = np.linalg.norm(np.diff(t[:, off[:-1]], axis=0), axis=2).max(axis=1) / 8
proof = json.loads((out / "motion_bound_proof.json").read_text())
axes[1, 1].plot(np.arange(2, 201), delta * 1000, label="root motion / 8")
axes[1, 1].axhline(
    proof["allowed_substep_displacement"] * 1000, color="red", ls="--", label="allowed displacement"
)
axes[1, 1].set(
    title="Prescribed roots already exceed the motion bound",
    ylabel="mm per substep",
    xlabel="frame",
)
axes[1, 1].legend(fontsize=8)
for ax in axes.ravel():
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.15)
fig.savefig(out / "real_diagnostics.png", dpi=160)
plt.close(fig)
