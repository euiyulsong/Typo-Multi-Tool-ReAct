# 오타 × multi-tool × one-shot/ReAct benchmark v3

`gpt-6-luna`, effort `none`. **모델 평가 결과는 포함하지 않습니다.** 로컬 검증은 mock API와 실제 sandbox 실행으로 수행했습니다.

## v2 검증에서 발견한 문제

v2는 모든 문항이 도시 ID 해석 → 가격/날씨 조회 → 합계 제출을 요구했습니다. One-shot은 첫 tool 응답을 모델에 다시 주지 않으므로 전체 task를 완료하기 어렵습니다. 기존 테스트는 이 실패만 확인했으며, one-shot이 성공 가능한 독립 multi-tool 요청을 확인하지 않았습니다. v2의 success=0을 오타 교정 성능으로 해석할 수 없습니다. 실제 사용자 로그의 생성 호출은 아래 진단 명령으로 확인하세요.

v3는 기본 100개를 **parallel 50개 / dependent 50개**로 나눕니다. 각 suite 안에서 intent/entity 오타가 25개씩입니다. 숫자와 tool schema는 유지하고 단어 내 인접 문자 전치를 넣습니다. 4개 입력 조건 × 2개 실행 방식 = 800 에피소드입니다.

| 입력 조건 | Agent에 전달하는 질문 | 교정 LLM 호출 |
|---|---|---:|
| clean | 오타 없는 원문 | 0 |
| raw | 오타 원문 | 0 |
| llm | spelling-only LLM 교정문 | 1 |
| term | character edit-distance 교정문 | 0 |

| suite | 정확한 tool 호출 | 성공 판정 |
|---|---|---|
| parallel | flight_lookup(origin,destination), hotel_lookup(city,nights), weather_lookup(city) | 세 조회의 tool/argument가 맞으면 성공 |
| dependent | resolve_city 2회 → flight_quote/hotel_quote/weather → finish_trip | 조회가 맞고 합계·날씨 제출이 맞으면 성공 |

Parallel은 세 tool이 모두 도시명을 직접 받습니다. 첫 입력만으로 세 호출을 생성할 수 있습니다. ReAct와 one-shot은 같은 suite의 동일 tool schema/menu/prompt를 받습니다. 별도의 final-answer 평가 호출은 없습니다. Parallel success는 조회 완료이며 합계 계산이나 자연어 답변 품질을 의미하지 않습니다.

One-shot은 한 agent 응답에 여러 tool call을 생성한 뒤 실행하고 종료합니다. Tool 결과를 받은 모델 재호출은 없습니다. ReAct는 반환 결과/오류를 tool_call_id와 함께 history에 붙여 최대 8회 agent 호출을 합니다. LLM 교정은 앞단 1회여서 one-shot/llm의 총 LLM 호출은 2회입니다. 같은 응답의 call은 sandbox에서 차례로 실행하지만 argument는 모두 이미 생성되어 있으며 중간 결과를 이용해 바뀌지 않습니다. 측정 latency는 sandbox 순차 실행을 포함하고 실서비스 parallel tool의 latency를 재현하지 않습니다.

## 실행

Python 3.10+, 표준 라이브러리만 사용합니다.

```bash
unzip typo_multitool_react.zip
cd typo_multitool_react
python3 benchmark.py --self-test
python3 test_loop.py
export OPENAI_API_KEY='YOUR_KEY'
# 필요할 때만: export OPENAI_BASE_URL='https://YOUR_ENDPOINT/v1'
# 두 suite를 하나씩 확인하려면 n=4 사용
python3 benchmark.py --model gpt-6-luna --n 4 --concurrency 1 --out smoke_v3
python3 benchmark.py --model gpt-6-luna --n 100 --concurrency 4 --out results_luna_v3
```

독립 multi-tool만 비교하려면:

```bash
python3 benchmark.py --suites parallel --n 100 --out parallel_v3
```

ReAct만 실행하려면 `--modes react`를 추가합니다. 기본 seed 42. `n=1`은 parallel/intent 한 문항입니다. 완료 항목 `(case_id, variant, mode)`를 재사용하며 config가 달라지면 새 `--out`이 필요합니다. v2 폴더에 v3 결과를 섞지 마세요. API 오류도 저장 완료 항목으로 처리하므로 재평가하려면 새 폴더를 사용하세요. 모델/effort fallback은 없습니다.

기존 결과 진단(API 호출 없음):

```bash
python3 diagnose.py results_luna_v22/predictions.jsonl
```

각 에피소드의 실제 tool 호출, 빠졌거나 argument가 다른 정답 call, 오류 및 실패 이유를 출력합니다. 이 진단은 저장한 trace의 해석이며 모델을 다시 실행하지 않습니다.

## 지표와 결과 파일

- `task_success`: suite별 작업 완료. 먼저 parallel/dependent를 따로 보세요.
- `tool_precision/recall/F1`: tool 종류 집합. 중복·argument 미반영.
- `call_multiset_exact`: tool 이름+전체 argument multiset의 완전 일치. 순서 미반영, 불필요 retry도 감점. 도시명 대소문자는 정규화합니다.
- `argument_call_precision/recall/F1`: 완전히 맞은 name+arguments 호출 단위 점수. 필드별 점수가 아닙니다.
- `first_step_call_f1/exact`: parallel은 최초 응답을 세 조회 정답과 비교. dependent는 최초 실행 가능한 두 resolve_city와 비교. suite 간 같은 의미의 전체 작업 지표로 비교하지 마세요.
- `failure_reason`, `missing_calls`: 실패 원인과 누락/잘못된 argument의 정답 call.
- `wall_seconds`, `correction_seconds`, `llm_calls`, `tokens`, `tool_errors`, `error`: 비용 및 오류.
- `correction_exact`: clean 텍스트 완전 일치인 보조 지표. 표면적인 문장 차이도 감점.

`summary.json/md`: suite × 오타 유형 × mode × 입력 조건. `paired.json`: 전체 pooled 결과에서 각 mode의 llm/term 대 raw, 같은 입력 조건의 ReAct 대 one-shot paired task-success 차이와 bootstrap CI, rescued/regressed 수. pooled delta와 함께 suite별 summary를 반드시 읽으세요. API 오류는 실패로 포함합니다.

`predictions.jsonl`: 질문/교정문/전체 trace/실제 calls/gold. `cases.jsonl`, `config.json`: 재현 정보와 benchmark version.

term은 배포용 tool 설명·공개 도시 목록·일반 travel vocabulary의 유일한 edit distance ≤1 후보를 사용합니다. adjacent transposition을 1회 편집으로 셉니다. 길이 4 미만, 이미 사전에 있는 단어, 최단거리 동률은 유지합니다. LLM 교정에도 같은 vocabulary를 제공합니다. 평가 질문/gold calls를 사전에 넣지 않습니다.

합성 영어 travel 문항이며 BFCL 공식 평가가 아닙니다. 실제 오타·한국어·미등록 고유명사로 일반화하려면 별도 평가가 필요합니다.

## 검증 범위

100개 문항의 sandbox oracle 검증, 800개 mocked 에피소드의 성공/실패 및 호출 횟수, parallel one-shot 성공, dependent one-shot 미완료, parallel call 누락 및 잘못된 argument 실패, boolean nights 거부, malformed correction 실패, 72개 summary group을 검증했습니다. 이는 실행/판정 코드 검증이며 GPT 모델 성능 검증이 아닙니다.
