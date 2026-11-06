# cad2swmm

[English](README.md) | [中文](README.zh.md) | **한국어** | [日本語](README.ja.md)

**CAD 배수 도면을 명령어 하나로 실행 가능한 EPA SWMM 모델로 변환합니다.**

GitHub의 모든 SWMM 자동화 도구는 GIS 데이터에서 출발합니다. 하지만 엔지니어는 배수 관망을
GIS로 그리지 않습니다 — CAD로 그립니다. `cad2swmm`는 바로 그 다리입니다. 맨홀과 관로가
그려진 DXF를 주면, EPA SWMM 5에서 열리고 그대로 실행되는 완전한 `.inp` 모델 파일을 돌려줍니다.

```bash
pip install ezdxf
python cad2swmm.py my_network.dxf -o my_network.inp
```

## 무엇을 하나요

| 도면에 있는 것 | 모델에 생성되는 것 |
|---|---|
| 노드 레이어의 맨홀 블록 / 점 / 원 | `[JUNCTIONS]` (+ `[OUTFALLS]`) |
| 블록 속성 `ID`, `INV` / `IL` / `ELEV`, 또는 `IL=12.34` 텍스트 | 노드 이름 및 관저 표고 |
| 관로 레이어의 `LINE` / `LWPOLYLINE` | 실제 기하 길이를 가진 `[CONDUITS]` |
| 관로 근처의 `DN300` / `D300` / `Φ300` / `300mm` 텍스트 | `[XSECTIONS]` 원형 관경 |
| 관저 표고 | 흐름 방향 자동 결정 (높은 곳 → 낮은 곳) |

조용히 누락되는 것은 없습니다. 관 끝점이 맨홀에 스냅되지 않으면 자동 노드를 만들고,
기본값으로 대체한 값(관경 라벨 없음, 표고 없음)은 어느 관·어느 맨홀인지와 함께
하나하나 경고로 보고합니다.

## 빠른 시작

```bash
# 번들 예제 도면을 생성한 뒤 변환 (도면 단위는 미터, 기본값)
python examples/make_example.py
python cad2swmm.py examples/example.dxf -o examples/example.inp

# 도면 단위가 밀리미터인 경우, 스모크 테스트 유입량 추가
python cad2swmm.py site.dxf -o site.inp --scale 0.001 --design-flow 50
```

번들 예제는 노드 5개, 관로 4개의 작은 관망으로, 엔지니어가 실제로 그리는 방식 그대로
그려져 있습니다(DXF는 `examples/make_example.py`가 생성):

```
nodes: 5 (junctions 4 + outfall OUT1)
conduits: 4, total length 115.0 m
```

출력은 직접 검증할 수 있습니다:

```bash
python tests/validate.py     # 구조 검사: 길이, 관경, 흐름 방향
pip install pyswmm
python tests/run_swmm.py     # 실제 EPA SWMM 엔진으로 모델 실행
```

엔진 실행은 스크린샷이 아니라 테스트의 일부입니다. 생성된 모델은 50 L/s 설계 유입량을
처음부터 끝까지 전달합니다(방류구 최대 유입 약 54 L/s, 동적파 효과 포함;
흐름 추적 연속성 오차 < 0.1%).

## 주요 옵션

```
--scale 0.001         도면 단위 -> 미터 (도면이 mm 단위면 0.001)
--node-layers 井,MANHOLE   맨홀/노드가 있는 레이어
--pipe-layers 管线,PIPE    관로가 있는 레이어
--default-diameter 0.3     DN 라벨이 없을 때 기본 관경 (m)
--default-invert 0.0       표고가 없을 때 기본 관저 표고 (m)
--outfall J9               방류구 노드 이름 (없으면 가장 낮은 노드)
--roughness 0.013          조도계수 (기본값: 콘크리트관)
--design-flow 50           가장 높은 접합부에 정유량 (L/s) 추가, 스모크 테스트용
--snap 2.0                 끝점-노드 스냅 허용 오차 (도면 단위)
```

## 도면 규칙

평소 그리던 대로 그리면 됩니다. 기본값은 영어와 중국어 CAD 레이어 관례를 모두 인식합니다.

- **노드**: `MANHOLE`, `NODE`, `检查井`, `井` 같은 레이어의 블록 참조, 점, 원
- **관로**: `PIPE`, `SEWER`, `管线`, `管道`, `排水` 같은 레이어의 선 / 폴리선
- **방류구**: 속성 `TYPE=OUTFALL`을 가진 노드 블록, 또는 `--outfall`로 지정
- DWG 파일: CAD에서 DXF로 다른 이름으로 저장하거나 ODA File Converter로 일괄 변환

Agent Skill로도 사용할 수 있습니다(`SKILL.md` 참조). SKILL.md를 지원하는 도구
(Claude Code, DeepSeek Harness 등)에 설치하고 "이 CAD 도면을 SWMM 모델로 바꿔줘"라고
말하면 됩니다.

## 로드맵

- DWG 직접 읽기 (ODA / LibreDWG)
- CAD 해치와 주석에서 소유역 및 강우 생성
- 오수 + 우수 이중 배제, 펌프/밸브 블록
- 시뮬레이션 실행과 Word 보고서를 위한 [agentic-swmm-workflow](https://github.com/Zhonghao1995/agentic-swmm-workflow) 연계 (선택)

## License

MIT
