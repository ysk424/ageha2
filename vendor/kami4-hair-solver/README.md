# Kami4 Hair Solver

Blender 5.2 / Windows x64 / CUDA の固定予算ヘアーソルバーです。C++20/CUDAコア、Blender拡張、T1～T3、実髪200フレーム、10万点ベンチマークを一つのリポジトリに実装しています。

**現在の復帰用基準点: `baseline-root2-200f-20260917`。** 根元2点固定、200Fを80.80秒、平均0.404秒/F。ソース・設定・DLL・シーン・キャッシュを対応付けた [復帰手順と既知の問題](docs/CHECKPOINTS.md) を保存しています。以下の初回検証資料には根元1点固定の結果も含みます。

**現時点の判定は不合格です。** 3試験と200フレームの計算・再生は動作しますが、元アニメーションの移動上限、一部のmesh接触、および厳密な微小残差のCPU/GPU相対比較に未達があります。完成した操作機能と、研究仮説の合否を区別しています。[実測結果](docs/RESULTS_JA.md)を参照してください。

今回の入力は、ポート9876で開いていた `kami-hair-solver` と同じ **「カーブ」6,757本・74,327点**、**「CC_Base_Body」225,184頂点・449,472三角形** です。元の `.blend` は上書きしていません。新しいシーンは `outputs/kami4_current_scene.blend`、拡張ZIPは `dist/kami4_hair_solver-0.1.0-windows-x64.zip` です。

## 使用

新しいシーンを開くと、`Kami4_髪_計算結果` と200フレームのキャッシュが接続済みです。3Dビューの「Kami4」で Replay を有効にし、タイムラインを動かしてください。再計算は Initialize → Bake、1フレームだけなら Simulate、開始形状へ戻す場合は Reset を使用します。Bake はEscで中止できます。

操作用キャッシュは `outputs/scene_cache` です。検証結果の原本 `outputs/real_final` は別に保存しています。シーンを別の場所へ移す場合はキャッシュもコピーし、Kami4パネルのパスを変更してください。

材質と固定回数は [extension/parameters.json](extension/parameters.json) の一つにあります。値を変更する際は新しいキャッシュフォルダーを指定して初期化します。入力する髪と身体メッシュは編集せず、計算結果を別のCurvesへ書き戻します。処理とキャッシュの詳細は [アーキテクチャ](docs/ARCHITECTURE.md) に記載しています。

## ビルドと再現

今回の環境: Blender 5.2.2 LTS、RTX 5070 Ti、driver 616.92、CUDA Toolkit 12.9.41、MSVC 19.44。C ABIヘッダーはC11/C++の両方で使用できます。

```powershell
./tools/build.ps1
ctest --test-dir build --output-on-failure
python tests/protocols.py --output outputs/protocols_final
python tests/benchmark.py
python tools/run_real.py --name real_final
python tools/replay_failure.py
python tools/package.py
```

`run_real.py` は今回保存した `outputs/input` を使います。元のBlender入力はユーザーのアセットなのでGitには含めません。`tests/blender_full_bake.py` は別名保存したシーンをBlender backgroundから読み、拡張のBake操作で200フレームを検証します。`tests/restart_replay.py` は別プロセスで200キャッシュのCRCと実際のCurvesへの再生を検証します。

FP64参照計算は検証専用です。Blender拡張から呼ばれるCPU fallbackではありません。

```powershell
python -m venv --system-site-packages .venv
./.venv/Scripts/python.exe -m pip install -r requirements-test.txt
./.venv/Scripts/python.exe -c "import sys; sys.path[:0]=['tests','extension']; import protocols; from cpu_oracle import CPUOracle; protocols.Solver=CPUOracle; protocols.run('outputs/protocols_cpu_final')"
```

## 構成

- `native/`: CUDA core、公開C ABI。
- `extension/`: 日本語UI、入力評価、native binding、CRC付きcache。
- `tests/`: 独立FP64 oracle、C ABI、物理3試験、性能、Blenderの操作と再起動再生。
- `tools/`: ビルド、入力抽出、最小失敗ケース、パッケージ作成。
- `docs/`: 原仕様、実装判断、実測値、未達事項。

ライセンス: GPL-3.0-or-later。元のkami / kami3リポジトリのコード・キャッシュは変更していません。
