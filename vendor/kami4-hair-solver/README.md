# Kami4 Hair Solver

Blender 5.2 / Windows x64 / CUDA のヘアーソルバーです。現在の画面名は **ACES**。線形曲げ・長さ補正・速度impulseを基本とし、身体メッシュのBVH接触と、残った接触を修復する局所FKを組み合わせています。

**2026-09-17 作業終了・再開時は [引き継ぎメモ](docs/RESUME_JA.md) を先に確認してください。** 87Fの画面を別名保存し、電源断用の一式を `session-end-20260917` に記録しています。

**現在の採用・復帰点は `baseline-local-fk-adopted-20260917` です。** 根元2点固定、曲げ剛性5e-7、最小計算長30cm、局所FK v2。採用済み200Fは106.94秒、平均0.535秒/F（計算とcache保存、レンダリングを除く）。実髪でのユーザー採用と、原仕様の全受入条件の合格は区別しています。

- [日本語の現行設計書](docs/ACES_DESIGN_JA.md)：原仕様との差分、処理図、数式、GPU配置、設定、検証範囲。
- [完全な採用パラメータ](presets/local-fk-contact-20260917.json)：材料の既定JSONだけでは採用状態を再現できません。
- [実験・採用記録](docs/experiments/local-fk-contact-20260917/README.md)と[復帰手順・全保存点](docs/CHECKPOINTS.md)。
- [採用Release](https://github.com/ysk424/kami4-hair-solver/releases/tag/baseline-local-fk-adopted-20260917)：対応するソース・拡張・シーン・200F cacheの保存点。

採用シーンは `outputs/local_fk_v2_200/kami4_aces_local_fk_v2.blend`、拡張は `dist/kami4_bvh_hair_solver-0.3.0-windows-x64.zip`。日本語Nパネル「ACES」で保存済みcacheを再生できます。元の入力blendは上書きしていません。再現計算は[設計書の手順](docs/ACES_DESIGN_JA.md#132-再計算する場合のコマンド)を使用し、既存の結果を上書きしないでください。

## 初版0.1.0の記録

以下は初版の操作・検証資料です。現在の拡張名、設定、保存先とは異なります。旧復帰点 `baseline-root2-200f-20260917` も保持しています（根元2点固定、200F 80.80秒、平均0.404秒/F）。初回検証には根元1点固定の結果も含みます。

**初版の一括受入判定は不合格でした。** 3試験と200フレームの計算・再生は動作しましたが、元アニメーションの移動上限、一部のmesh接触、および厳密な微小残差のCPU/GPU相対比較に未達がありました。[初版の実測結果](docs/RESULTS_JA.md)を参照してください。

今回の入力は、ポート9876で開いていた `kami-hair-solver` と同じ **「カーブ」6,757本・74,327点**、**「CC_Base_Body」225,184頂点・449,472三角形** です。元の `.blend` は上書きしていません。新しいシーンは `outputs/kami4_current_scene.blend`、拡張ZIPは `dist/kami4_hair_solver-0.1.0-windows-x64.zip` です。

### 初版の使用

新しいシーンを開くと、`Kami4_髪_計算結果` と200フレームのキャッシュが接続済みです。3Dビューの「Kami4」で Replay を有効にし、タイムラインを動かしてください。再計算は Initialize → Bake、1フレームだけなら Simulate、開始形状へ戻す場合は Reset を使用します。Bake はEscで中止できます。

操作用キャッシュは `outputs/scene_cache` です。検証結果の原本 `outputs/real_final` は別に保存しています。シーンを別の場所へ移す場合はキャッシュもコピーし、Kami4パネルのパスを変更してください。

材質と固定回数は [extension/parameters.json](extension/parameters.json) の一つにあります。値を変更する際は新しいキャッシュフォルダーを指定して初期化します。入力する髪と身体メッシュは編集せず、計算結果を別のCurvesへ書き戻します。処理とキャッシュの詳細は [アーキテクチャ](docs/ARCHITECTURE.md) に記載しています。

### 初版のビルドと再現

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
