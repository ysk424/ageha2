import json, hashlib, platform, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


def read(path):
    return json.loads((OUT / path).read_text(encoding="utf8"))


gpu = read("protocols_final/report.json")
cpu = read("protocols_cpu_final/report.json")
real = read("real_final/report.json")
bench = read("blender_benchmark.json")
full = read("blender_full_bake.json")
replay = read("restart_replay.json")
motion = read("motion_bound_proof.json")
minimal = read("minimal_mesh_failure/report.json")
meta = read("input/manifest.json")
profiles = read("bucket_profile.json")
binary = hashlib.sha256((ROOT / "extension/bin/kami4_hair_core.dll").read_bytes()).hexdigest()
package = hashlib.sha256(
    (ROOT / "dist/kami4_hair_solver-0.1.0-windows-x64.zip").read_bytes()
).hexdigest()
comparison = {}
for test in ("T1", "T2", "T3"):
    comparison[test] = {}
    for metric in (
        "height",
        "left_material",
        "right_material",
        "max_length_error",
        "p99_length_error",
        "min_gap",
    ):
        a = cpu[test]["final"][metric]
        b = gpu[test]["final"][metric]
        comparison[test][metric] = dict(
            cpu=a,
            gpu=b,
            absolute_difference=abs(a - b),
            relative_difference=abs(a - b) / abs(a) if abs(a) > 1e-10 else None,
        )
    comparison[test]["slip_frame_cpu"] = cpu[test].get("slip_frame")
    comparison[test]["slip_frame_gpu"] = gpu[test].get("slip_frame")
rows = [json.loads(l) for l in (OUT / "real_final/stats.jsonl").read_text().splitlines()]
assert len(rows) == 200 and [r["frame"] for r in rows] == list(range(1, 201))
assert bench["binary_hash"] == binary, ("benchmark binary mismatch", bench["binary_hash"], binary)
assert full["binary_hash"] == binary, (
    "Blender full bake binary mismatch",
    full["binary_hash"],
    binary,
)
assert read("real_final/manifest.json")["binary_hash"] == binary
assert all(
    x["parameter_hash"] == gpu["parameter_hash"] for x in [cpu, real, bench, full, replay, profiles]
)
tests_motion = {
    name: sum(r["motion_violations"] for r in read(f"protocols_final/{name}.json"))
    for name in ["T1", "T2", "T3", "T3_mu0"]
}
checks = dict(
    T1=gpu["T1"]["pass"],
    T2=gpu["T2"]["pass"],
    T3=gpu["T3"]["pass"],
    protocol_motion_bound=all(x == 0 for x in tests_motion.values()),
    common_parameters=True,
    real_200_complete=real["checks"]["completed"],
    real_length=real["checks"]["length"] and real["checks"]["p99"],
    real_contact=real["checks"]["penetration"],
    real_motion=real["checks"]["motion"],
    synthetic_100k=bench["pass"],
    real_full_frame_realtime=full["full_blender_frame_ms_median"] <= 41.7,
    cache_restart=replay["pass_"],
    strict_T1_residual_relative_2pct=comparison["T1"]["max_length_error"]["relative_difference"]
    <= 0.02,
)
result = dict(
    status="PASS" if all(checks.values()) else "FAIL",
    checks=checks,
    binary_hash=binary,
    package_hash=package,
    parameter_hash=gpu["parameter_hash"],
    gpu=bench["gpu"],
    blender=bench["blender"],
    python=platform.python_version(),
    material=gpu["parameters"],
    input=meta,
    protocols=gpu,
    cpu_gpu=comparison,
    real=real,
    synthetic=bench,
    blender_full=full,
    cache_restart=replay,
    motion_bound=motion,
    minimal_failure={k: v for k, v in minimal.items() if k != "stats"},
    fixed_launch_counts=sorted(set(r["launches"] for r in rows)),
    protocol_motion_violations=tests_motion,
)
(OUT / "acceptance.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8"
)
(OUT / "cpu_gpu_comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf8")
t1, t2, t3 = (gpu[x] for x in ("T1", "T2", "T3"))
loss = t2["final"]["left_material"] - t3["final"]["left_material"]
b = bench
text = f"""# Kami4 実行結果 — 2026-09-17

**一括受入: 不合格。** 動作するBlender拡張、200frameの計算・cache再生、3試験、10万点benchmarkを作成した。未達を成功とは扱わない。機械可読の全判定は [acceptance.json](../outputs/acceptance.json)。

## 保存場所と入力

- 新規repo: `C:/Users/azoo/git/kami4-hair-solver`
- [現在のBlenderと同じ入力を接続したシーン](../outputs/kami4_current_scene.blend)
- [拡張のBake操作で検証したシーン](../outputs/kami4_verified_bake.blend)
- [インストール用ZIP](../dist/kami4_hair_solver-0.1.0-windows-x64.zip)
- [共通parameter JSON](../extension/parameters.json)

保存シーンの操作用cacheは `outputs/scene_cache`。検証結果の原本 `outputs/real_final` とは別にしている。現在のBlenderで Reset → Simulate → Replay を実行し、保存済み1Fと座標が完全一致することを確認した。[実操作の確認](../outputs/live_verification.json)

ヘアーは「カーブ」{meta["strands"]:,}本・{meta["points"]:,}点。コライダーは「CC_Base_Body」{meta["vertices"]:,}頂点・{meta["triangles"]:,}三角形。原ファイル `{meta["original_blend"]}` は上書きしていない。元のkami / kami3のcode・cacheも変更していない。

## 判定表

| 項目 | 実測 | 判定 |
|---|---|---|
| T1 中央圧縮 | 高さ {t1["final"]["height"]:.6f} m、頂点x {t1["final"]["peak_x"]:.6f} m、主要airborne region 1個 | 試験条件合格 |
| T2 円柱落下 | 最高点 {t2["final"]["height"]:.6f} m、左右材料長差 {t2["final"]["symmetry"]:.3g} m | 試験条件合格 |
| T3 片側引張り | 左側材料長 {loss:.6f} m減少、摩擦ありslip {t3["slip_frame"]}F、mu=0は {gpu["T3_mu0"]["slip_frame"]}F | 試験条件合格 |
| 3試験の共通設定 | B=1e-6、damping=8、mu=0.35、substeps/P/I=4/3/3 | 合格 |
| 実髪完走 | 200/200F、NaN/Inf・strand脱落・fatal errorなし | 合格 |
| 実髪長さ | 最大 {real["max_length_error"] * 100:.5f}%、p99 {real["p99_length_error"] * 100:.6f}% | 合格 |
| 実髪node接触 | 最大 {-real["min_gap"] * 1e6:.3f} µm侵入、許容10 µm | **不合格** |
| 移動上限 | 最大8分割でも指定root移動が上限の {motion["ratio_at_8"]:.2f}倍 | **不合格** |
| 合成10万点 | warm-up 120 + 計測600F、接触点 {b.get("contact_count_range")} | 合格 |
| 合成性能 | native中央値 {b["native_median"]:.3f} ms、Blender書き戻し込み {b["blender_total_median"]:.3f} ms | 合格 |
| cache | 別Blenderプロセスで200frame CRC検査、1/7/100/200Fを実再生 | 合格 |
| CPU/GPU最終形 | 高さ・左右材料長は2%以内、slip開始は一致、T1微小残差の相対2%は未達 | **厳密比較は不合格** |

3試験はXY拘束した同一3D kernelで実行した。試験fps=240、T1=8秒、T2=5秒、T3=8秒。T1は100辺・L=1mの共通rest lengthで中央seedから開始し、0.36m圧縮する。T3はT2の位置と速度を引き継ぎ、右端を0.18m引く。試験内の移動上限違反は {tests_motion}。

![3試験](figures/three_tests.png)

## 実シーンの速度

評価済み入力を再生した実髪200Fは、native中央値 **{real["native_ms_median"]:.3f} ms**、CPU転送・位置取得込み **{real["total_ms_median"]:.3f} ms**。

Blender拡張のBake操作では、身体と髪の評価を含め200Fを **{full["seconds"]:.2f}秒**、平均 **{full["seconds"] / full["frames"]:.3f}秒/frame**、中央値 **{full["full_blender_frame_ms_median"]:.2f} ms/frame**。その実行中のnative中央値は **{full["native_ms_median"]:.2f} ms**。独立ベンチマークと実シーン内の時間を混同しない。この実シーン全体は24fps動作ではない。native時間差の原因はここでは断定していない。ここで測定したのはヘアー計算・cache保存であり、Cycles/Eeveeの画像レンダリング時間は未測定。

拡張Bakeの最終座標と評価済み入力を使ったnative実行との差は **{full["max_difference_from_exported_run"]} m**。入力の評価座標も抽出時から2e-7m以内で一致した。

![実髪診断](figures/real_diagnostics.png)

入力評価だけを1〜15Fで計測した別のprobeでは、frame変更252.46ms、髪取得67.56ms、mesh取得58.38ms、合計378.34msだった。非入力objectを隠した場合380.53ms、評価済みmeshを直接読む場合380.08msで改善しなかったため、これらの変更は採用していない。[測定値](../outputs/blender_evaluation_probe.json)

## 未達の再現

1. 最短辺は {motion["min_edge"]:.9f}m、移動上限は {motion["allowed_substep_displacement"]:.9f}m/substep。{motion["frame"]}Fの指定root移動は {motion["maximum_root_frame_displacement"]:.9f}m/frame。8分割でも {motion["minimum_root_substep_displacement_at_8"]:.9f}m。strandごとの最短辺で条件を緩めても、strand {motion["per_strand_bound_worst"]["strand"]}で {motion["per_strand_bound_worst"]["ratio_at_8"]:.2f}倍。これはsolve前に決まるkinematic入力の問題であり、収束反復では解消できない。[数値と最小入力](../outputs/motion_bound_proof.json)
2. mesh接触の失敗はstrand {minimal["original_strand"]}、11点、{minimal["triangles"]:,}三角形へ縮小して再現した。7Fで約31.6µmのsurface侵入が残る。`python tools/replay_failure.py` でBlenderなしに再現できる。[fixture](../outputs/minimal_mesh_failure/fixture.npz)
3. T1の最終max辺長残差はCPU {comparison["T1"]["max_length_error"]["cpu"]:.3g}、GPU {comparison["T1"]["max_length_error"]["gpu"]:.3g}。両者とも物理試験の1%を十分下回るが、残差自体を分母にした2%相対一致は満たさない。許容条件を変更して合格にはしていない。[全scalar比較](../outputs/cpu_gpu_comparison.json)

## 実装と検証の範囲

- C++20/CUDA、opaque handleのC ABI。C11 consumerによる作成・prepare・step・download・破棄を検証した。
- 独立oracle等のPython 15テストが合格。非均一辺長、全6bucket、曲げ、長さ、全解析形状、摩擦、動くplane、無接触全経路、修復したroot tangent、CRC破損を含む。
- 全frameでdevice allocation=0、実髪のkernel数={result["fixed_launch_counts"]}。CUDA Graphは初期化時に一度だけ作成。
- 短strandは1 thread、長strandはblockでaffine prefix/PCR。profileは [bucket_profile.json](../outputs/bucket_profile.json)。
- Initialize / Simulate / Reset / Bake / Replayと、再起動後のcache再生を検証した。
- mesh接触はユーザーの入力指定を優先して追加した両面node/surface方式。edge接触・体積内外保証・CCDはない。
- 投影による支持impulseの整合処理を明示的に加えている。[数式上の補足と構造](ARCHITECTURE.md)

次の方式は [ADR](ADR-001-acceptance.md) に一つだけ記した。原仕様を変更した合格版や、CPU fallback・表示補正で隠した結果としては提出しない。

## 環境・hash

{bench["gpu"]} / Blender {bench["blender"]} / CUDA Toolkit 12.9.41 / MSVC 19.44。

- binary SHA256: `{binary}`
- parameter SHA256: `{gpu["parameter_hash"]}`
- package SHA256: `{package}`
"""
(ROOT / "docs/RESULTS_JA.md").write_text(text, encoding="utf8")
print(json.dumps(dict(status=result["status"], checks=checks), ensure_ascii=False, indent=2))

summary={k:result[k] for k in ("status","checks","binary_hash","package_hash","parameter_hash","gpu","blender","material","real","synthetic","blender_full","motion_bound","fixed_launch_counts")}
(ROOT/"docs/acceptance_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
