# cad2swmm

[English](README.md) | [中文](README.zh.md) | **한국어** | [日本語](README.ja.md)

저는 건축 배수 설계를 하는 사람입니다. 프로젝트가 끝날 때마다 늘 같은
작업이 남습니다. CAD 도면은 다 그렸는데, SWMM을 열고 맨홀, 파이프, 관경,
관저 표고를 처음부터 다시 입력해야 합니다. 이미 도면 안에 있는 데이터인데
말이죠. 그 일을 몇 번 반복하다가 이 도구를 만들었습니다.

cad2swmm는 DXF 배수 도면을 읽어 EPA SWMM 5에서 바로 열고 실행할 수 있는
`.inp` 파일을 만듭니다. 하는 일은 이것 하나뿐이지만, 가장 지루한 한 시간을
없애 줍니다. GitHub의 다른 SWMM 도구들은 전부 GIS 데이터에서 시작하는데,
엔지니어는 배수 관망을 GIS로 그리지 않기 때문에 CAD 단계가 비어 있었습니다.

```bash
pip install ezdxf
python cad2swmm.py my_network.dxf -o my_network.inp
```

## 도면에서 읽는 것

- 맨홀: 노드 레이어의 블록, 점, 원 → 접합점(junction)과 방류구(outfall)
- 노드 이름과 관저 표고: 블록 속성(`ID`, `INV` / `IL` / `ELEV`) 또는
  `IL=12.34` 같은 텍스트
- 파이프: 파이프 레이어의 선과 폴리라인 → 관로(conduit), 길이는 도형에서 실측
- 관경: 파이프 근처의 `DN300` / `D300` / `Φ300` / `300mm` 라벨
- 흐름 방향: 표고를 따라 높은 곳에서 낮은 곳으로 자동 결정

파이프 끝점이 맨홀에 붙지 않으면 노드를 새로 만듭니다. 관경 라벨이나 표고가
없어서 추정한 값은 어느 파이프, 어느 맨홀인지 이름과 함께 경고로 출력합니다.
조용히 숫자를 지어내지는 않습니다.

## 예제 실행

`examples` 폴더에 노드 5개, 파이프 4개의 작은 관망이 들어 있습니다(DXF는
스크립트로 생성하므로 첫 명령을 먼저 실행하세요).

```bash
python examples/make_example.py
python cad2swmm.py examples/example.dxf -o examples/example.inp

# 도면 단위가 mm이고 50 L/s 테스트 유입을 넣고 싶을 때
python cad2swmm.py site.dxf -o site.inp --scale 0.001 --design-flow 50
```

변환 결과:

```
nodes: 5 (junctions 4 + outfall OUT1)
conduits: 4, total length 115.0 m
```

테스트 스크립트가 세 개 있는 이유는 스크린샷이 아니라 증거가 필요했기
때문입니다. `tests/validate.py`는 구조(길이, 관경, 흐름 방향)를 검사하고,
`tests/run_swmm.py`는 pyswmm으로 실제 EPA SWMM 엔진에서 생성된 모델을
실행합니다. 50 L/s 설계 유입이 끝까지 전달되고, 방류구 첨두는 동적파
효과를 포함해 약 54 L/s, 흐름 추적 연속성 오차는 0.1% 미만입니다.
`tests/run_pipeline.py`는 아래 전체 파이프라인을 검증합니다. 산출물
세 가지가 모두 생성되고, 보고서의 수치가 .rpt 원문과 일치하는지
확인합니다.

## 전체 파이프라인: 도면 → 시뮬레이션 → 중국어 검수 보고서

변환은 첫 단계일 뿐입니다. `--pipeline`을 붙이면 같은 스크립트가 끝까지
진행합니다. pyswmm으로 실제 SWMM 엔진에서 `.inp`를 실행하고, `.rpt`를
중국어 검수 보고서(Markdown)로 만듭니다. 연속성 오차 판정, 방류구 유량
요약, 침수/과부하 노드와 만관 파이프 목록까지, 모든 수치는 .rpt 원문
그대로입니다.

```bash
pip install pyswmm
python cad2swmm.py examples/example.dxf --pipeline --outdir examples/pipeline --design-flow 50
```

`examples/pipeline/`의 파일들이 바로 이 명령의 실제 산출물입니다.
단계별 실행도 됩니다. `--run`은 시뮬레이션만, `--report`는 보고서만
만듭니다. 이미 `.inp`나 `.rpt`가 있으면 파일 자체를 입력으로 넘겨
후반 단계만 쓸 수 있습니다.

```bash
python cad2swmm.py model.inp --run --report
python cad2swmm.py model.rpt            # 검수 보고서만
```

보고서는 이 저장소에 포함된 `swmm_report_cn/` 패키지(swmm-report-cn,
MIT, 표준 라이브러리만 사용)가 생성하므로 별도 설치가 필요 없습니다.

## 주요 옵션

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

## 도면 작성 규칙

평소 그리던 대로 그리면 됩니다. 기본값이 영어와 중국어 레이어 이름을
모두 인식합니다.

- 노드: `MANHOLE`, `NODE`, `检查井`, `井` 같은 레이어의 블록 참조, 점, 원
- 파이프: `PIPE`, `SEWER`, `管线`, `管道`, `排水` 같은 레이어의 선 / 폴리라인
- 방류구: `TYPE=OUTFALL` 속성을 가진 노드 블록, 또는 `--outfall` 지정
- DWG 파일: CAD에서 DXF로 다시 저장(또는 ODA File Converter로 일괄 변환)

## 아직 안 되는 것

- DWG 직접 읽기
- 소유역과 강우 — 이 부분은 아직 직접 나눠야 합니다
- 펌프, 밸브, 오수+우수 이중 시스템

SKILL.md를 지원하는 도구(Claude Code, DeepSeek Harness 등)에서는 에이전트
스킬로도 쓸 수 있습니다(`SKILL.md` 참조).

## License

MIT
