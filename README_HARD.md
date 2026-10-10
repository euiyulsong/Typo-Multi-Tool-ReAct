# Hard multi-tool typo benchmark

기존 1문항의 100%는 smoke 결과였습니다. 이번 버전은 독립 multi-tool 요청 100개에서 네 입력 조건(clean/raw/llm/term) × 두 방식(one_shot/react)을 평가합니다. **모델 성능 결과는 아직 없으며, 더 낮은 성공률을 보장하지 않습니다.**

## 난이도 변경

| 항목 | 기존 parallel | hard |
|---|---|---|
| 정답 calls | 3 | 8 |
| tool menu | 6개 | 15개 |
| 선택 | flight/hotel/weather 고정 | 가격·좌석·빈방·예보·과거 날씨·소요시간·메뉴·테이블 구분 |
| 도시 | 출발·목적지 | 출발·경유·목적지·취소 도시 |
| argument | 도시·숙박일수 | 구간 방향·날짜·인원·객실·좌석 등급·환불 여부·온도 단위 |
| 문맥 | 단순 요청 | 취소된 계획 후 최종 일정, 예약/경고 제외 |
| 오타 | 문자 전치 1회 | 전치·삭제·치환, 위치당 1/2회 편집 시도 |

각 요청: 비행 2구간, 호텔 2도시, 미래 날씨 1개, 과거 날씨 1개, 기차 조회 1개, 식당 조회 1개. Task마다 가격 vs 가용성, 기차 요금 vs 소요시간, 식당 메뉴 vs 테이블 가용성을 바꿉니다. 15개 schema의 순서는 문항별로 섞고 같은 문항의 조건 간에는 유지합니다.

Intent 오타는 최대 6개 단어 위치, entity 오타는 경유지·목적지 도시명 전체 등장 위치에 같은 오타를 넣습니다. 각 유형 50개이며 severity 1/2가 각 25개씩입니다. severity는 편집 시도 횟수입니다. 실제 edit distance는 편집 상쇄나 같은 문자 치환으로 달라질 수 있습니다. 숫자·날짜·true/false·refundable·취소/제외 표현은 intent 오타 주입에서 보호합니다. 숫자형 문맥 제약은 유지되지만 cabin/unit 값도 오타 대상이 될 수 있습니다. 공개 vocabulary와 tool 설명은 term/LLM 교정 모두에 제공하며, 평가 질문/gold는 교정 입력에 주지 않습니다. Term은 종전과 같은 edit distance ≤1 전략이므로 두 편집 오타를 고치지 못할 수 있습니다.

Tool은 모두 독립적으로 원문에서 argument를 얻을 수 있습니다. One-shot도 첫 응답에 8개 호출을 생성해 성공할 수 있습니다. ReAct는 실패한 lookup 결과를 보고 수정할 수 있습니다. 교정은 처음 한 번이며 ReAct 내부에서 추가 교정 호출을 강제하지 않습니다.

성공 조건: 요구한 8개 name+arguments 조회가 모두 유효하게 실행되고, 요청하지 않은 tool 종류를 호출하지 않아야 합니다. 잘못된 argument를 사용한 같은 종류의 조회는 ReAct에서 수정할 수 있습니다. Tool 종류가 다른 불필요 호출, 특히 예약 tool 사용은 이후 올바른 조회를 해도 실패입니다. 중복/잘못된 조회는 call exact/argument precision에도 반영됩니다. Tool 결과는 deterministic synthetic numeric fixture이며 자연어 final answer 품질을 평가하지 않습니다.

## 실행

Python 3.10+ 표준 라이브러리만 사용합니다.

```bash
unzip typo_multitool_react_hard.zip
cd typo_multitool_react
python3 hard.py --self-test
export OPENAI_API_KEY='YOUR_KEY'
# 필요할 때만: export OPENAI_BASE_URL='https://YOUR_ENDPOINT/v1'
python3 hard.py --model gpt-6-luna --n 4 --concurrency 1 --out hard_smoke
python3 hard.py --model gpt-6-luna --n 100 --concurrency 4 --out results_hard_luna
```

hard.py는 parallel 전용입니다. benchmark.py에는 이전 parallel/dependent 실험이 남아 있습니다. 이번 결과는 새 폴더에 저장하세요. 동일 config로 재실행하면 checkpoint를 재사용합니다. LLM correction은 agent 호출 외에 1회를 추가하고, 지연은 이 교정 비용을 포함합니다. ReAct의 max_steps 기본 8회. One-shot의 agent 호출은 정확히 1회입니다.

API 없이 문항만 준비하려면:

```bash
python3 hard.py --n 100 --prepare-only --out hard_cases
```

출력: summary.md/json, predictions.jsonl, paired.json, cases.jsonl, config.json. Predictions에는 severity, 전체 trace와 누락된 정답 call도 들어 있습니다. Task_success와 call exact를 우선 비교하고 argument F1, tool F1, 교정 overhead·latency를 함께 읽으세요. 1문항으로 승자를 판단하지 마세요.

`python3 diagnose.py results_hard_luna/predictions.jsonl`로 실행별 호출을 확인할 수 있습니다. 실제 모델이 100%를 유지한다면 실사용 로그나 더 넓은 도메인으로 검증해야 합니다. 이 데이터는 합성 영어 travel benchmark이며 BFCL 공식 점수가 아닙니다.

## 코드 검증

100문항 재현성·고유성, 8개 정답 call의 실행, 각 call 누락 실패, 인원 argument 오류 실패, 제외된 예약 호출 실패, 800개 mocked one-shot/ReAct 실행 및 호출 횟수를 확인했습니다. 이전 v3의 회귀 테스트도 통과했습니다. 이 검증은 모델 정확도를 측정하지 않습니다.
