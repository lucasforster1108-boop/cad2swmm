# cad2swmm

[English](README.md) | [中文](README.zh.md) | [한국어](README.ko.md) | **日本語**

私は建築の排水設計をしている人間です。プロジェクトの最後はいつも同じ
作業が残ります。CAD 図面は描き終わったのに、SWMM を開いてマンホール、
管、管径、管底高を最初から打ち直す。データは図面の中にもうあるのに、
です。その作業を何度か繰り返して、これを作りました。

cad2swmm は DXF の排水図面を読み、EPA SWMM 5 でそのまま開いて実行できる
`.inp` ファイルを書き出します。やることはこれ一つだけですが、いちばん
面倒な 1 時間が消えます。GitHub の他の SWMM ツールはどれも GIS データ
から始まりますが、エンジニアは排水管網を GIS で描かないので、CAD の
一段が抜けていました。

給水側の同じ面倒もここに引っ越してきました。`cad2epanet.py` は EPANET
に対して同じことをします。DXF の給水図面を読み、実行できる EPANET 2.2
の `.inp` を書き出します。もとは独立したリポジトリ（cad2epanet）でした
が、2 つの変換ツールの仕組みの大半は共通なので、このリポジトリに統合
しました。DXF の読み取り、端点の吸着、ラベルの照合は共有モジュール
`dxfnet.py` に移し、各スクリプトには自分のモデルの意味だけが残って
います。

```bash
pip install ezdxf
python cad2swmm.py my_network.dxf -o my_network.inp
```

## 図面から読むもの

- マンホール：ノードレイヤー上のブロック・点・円 → ジャンクションと放流口
- ノード名と管底高：ブロック属性（`ID`、`INV` / `IL` / `ELEV`）、または
  `IL=12.34` のような文字
- 管：管レイヤー上の線分とポリライン → 管路（長さはジオメトリから実測）
- 管径：管の近くの `DN300` / `D300` / `Φ300` / `300mm` ラベル
- 流向：管底高に従い、高い方から低い方へ自動で決定

管の端点がマンホールに吸着しない場合は、ノードを自動で作ります。管径
ラベルや管底高がなくて推定した値は、どの管・どのマンホールか名前付きで
警告として出力します。黙って数字をでっち上げることはしません。

## まず例を動かす

`examples` フォルダにノード 5 個、管 4 本の小さな管網が入っています
（DXF はスクリプト生成なので、最初のコマンドを先に実行してください）。

```bash
python examples/make_example.py
python cad2swmm.py examples/example.dxf -o examples/example.inp

# 図面の単位が mm で、50 L/s のテスト流入を入れる場合
python cad2swmm.py site.dxf -o site.inp --scale 0.001 --design-flow 50
```

変換結果：

```
nodes: 5 (junctions 4 + outfall OUT1)
conduits: 4, total length 115.0 m
```

テストスクリプトが 3 つあるのは、スクリーンショットではなく証拠が
欲しかったからです。`tests/validate.py` は構造（管長、管径、流向）を
検査し、`tests/run_swmm.py` は pyswmm 経由で本物の EPA SWMM エンジンで
生成モデルを実行します。50 L/s の設計流入が最後まで流れ、放流口の
ピークは動力波の影響込みで約 54 L/s、流量ルーティングの連続性誤差は
0.1% 未満です。`tests/run_pipeline.py` は下のパイプライン全体を検証し、
生成物 3 点の存在と、レポートの数値が .rpt 原文と一致することを
確認します。

## パイプライン：図面 → シミュレーション → 中国語校核レポート

変換は最初の一歩にすぎません。`--pipeline` を付けると、同じスクリプト
が最後まで進みます。pyswmm で本物の SWMM エンジンで `.inp` を実行し、
`.rpt` を中国語の校核レポート（Markdown）に変換します。連続性誤差の
判定、放流口の流量集計、浸水・過負荷ノードと満管の管の一覧まで、数値は
すべて .rpt 原文のままです。

```bash
pip install pyswmm
python cad2swmm.py examples/example.dxf --pipeline --outdir examples/pipeline --design-flow 50
```

`examples/pipeline/` のファイルが、このコマンドの実際の生成物です。
段階ごとの実行もできます。`--run` はシミュレーションのみ、`--report`
はレポートのみ。すでに `.inp` や `.rpt` がある場合は、そのファイルを
入力として渡せば後段だけ使えます。

```bash
python cad2swmm.py model.inp --run --report
python cad2swmm.py model.rpt            # 校核レポートのみ
```

レポートはこのリポジトリに同梱された `swmm_report_cn/` パッケージ
（swmm-report-cn、MIT、標準ライブラリのみ）が生成するので、追加の
インストールは不要です。

## cad2epanet：給水側

```bash
python cad2epanet.py my_water_network.dxf -o my_water_network.inp
```

図面から読むもの：

- ノード：ノードレイヤー上のブロック・点・円 → ジャンクション、
  リザーバ、タンク
- ノード名と地盤高：ブロック属性（`ID`、`ELEV` / `EL` / `INV` / `IL`）、
  または `EL=52.30` のような文字。需要量は `DEMAND` 属性（L/s）
- 水源：`TYPE=RESERVOIR` 属性のノード。全水頭は `HEAD` 属性から。
  なければ標高 + `--source-head` として警告を出します（隠しません）。
  水源が一つもなければ最も高いノードを使い、これも警告付きです
- タンク：`TYPE=TANK` ノード。水位と直径は `--tank-*` オプション
- 管と管径の読み方は排水側とまったく同じです

排水との本質的な違いが一つあります。給水は圧力流れなので、**管は標高
で方向付けしません**。管は 2 点をつなぐだけで、流れの向きは EPANET が
計算します。

給水側にも同じ 5 ノードの例があります（`examples/make_example_epanet.py`
が `example_epanet.dxf` を生成します）。

```bash
python examples/make_example_epanet.py
python cad2epanet.py examples/example_epanet.dxf -o examples/example_epanet.inp
```

```
nodes: 5 (junctions 4 + reservoir R1)
pipes: 4, total length 115.0 m
total base demand: 16 L/s
```

給水側のテストは 2 つです。`tests/validate_epanet.py` は構造と、全
ジャンクションが水源までつながっていることを確認します。
`tests/run_epanet.py` は WNTR 経由で本物の EPANET エンジンで実行し
ます。水源の流出はちょうど 16.00 L/s で全基準需要量と一致し、
ジャンクションの圧力は 11.95〜14.93 m。115 m の管でこの流量なら
妥当な損失水頭です。

cad2swmm と異なるオプション（`--scale`、`--snap`、`--node-layers`、
`--pipe-layers`、`--default-diameter` は同じ）：

```
--default-elevation 0.0    fallback ground elevation (m) when no EL text is found
--roughness-c 130          Hazen-Williams C (130 = new cast iron / DI)
--reservoir J9             source node name (else TYPE=RESERVOIR, else highest node)
--source-head 10           head (m) added to elevation when a reservoir has no HEAD
--tank-diameter 10         diameter (m) for TYPE=TANK nodes
--tank-init-level 2        initial level (m) for TYPE=TANK nodes
--tank-max-level 5         max level (m) for TYPE=TANK nodes
```

## 主なオプション

```
--scale 0.001         drawing units -> metres (0.001 if the drawing is in mm)
--node-layers 井,MANHOLE   layers that hold manholes/nodes
--pipe-layers 管线,PIPE    layers that hold pipes
--default-diameter 0.3     fallback diameter (m) when no DN label is found
--default-invert 0.0       fallback invert elevation (m)
--outfall J9               name of the outfall node (else: lowest node)
--roughness 0.013          Manning's n (default: concrete pipe)
--design-flow 50           add a constant inflow (L/s) at the highest junction
--snap 2.0                 endpoint-to-node snap tolerance (drawing units)
--pipeline                 full pipeline: convert -> run -> Chinese check report (implies --run --report)
--run                      run the .inp in the SWMM engine (pyswmm), producing a .rpt
--report                   generate a Chinese check report (.md) from the .rpt
--outdir DIR               directory for pipeline products (.inp/.rpt/report)
--report-output PATH       explicit path for the check report .md
```

## 図面の描き方

普段の描き方で大丈夫です。デフォルトで英語と中国語のレイヤー名の両方を
認識します。

- ノード：`MANHOLE`、`NODE`、`检查井`、`井` などのレイヤー上のブロック
  参照、点、円
- 管：`PIPE`、`SEWER`、`管线`、`管道`、`排水` などのレイヤー上の線分 /
  ポリライン
- 放流口：`TYPE=OUTFALL` 属性を持つノードブロック、または `--outfall`
- DWG ファイル：先に CAD で DXF に別名保存（または ODA File Converter
  で一括変換）

## まだできないこと

- DWG の直接読み込み
- 集水区と降雨 — ここはまだ自分で区切る必要があります
- ポンプ、バルブ、雨水・汚水の二重システム
- EPANET 側：需要パターンと長時間シミュレーション — 生成されるモデル
  は定常状態のスナップショット 1 つだけです。ポンプ曲線、制御弁、消火
  流量、水質計算も未対応です

SKILL.md に対応するツール（Claude Code、DeepSeek Harness など）では、
エージェントスキルとしても使えます（`SKILL.md` 参照）。

## License

MIT
