# AI Commit/PR Generator

`git status`와 `git diff`를 수집해 AI API로 **커밋 메시지**와 **PR 제목/본문 초안**을 만드는 Python CLI입니다.
생성 결과는 길이·템플릿 규칙으로 검증한 뒤 구분선으로 나눠 터미널에 출력하고, 사용자가 검토한 다음 적용합니다.

```text
git status / git diff ─▶ safe-mode(마스킹·전송 제한) ─▶ 프롬프트 구성 ─▶ AI API(REST) 1회 호출
                                                                         │
            터미널 출력(구분선) ◀── 후처리 ◀── 형식 검증 ◀── JSON 응답 파싱 ◀┘
```

- 외부 패키지 없이 표준 라이브러리(`urllib`, `subprocess`, `argparse`)로 구현했습니다. `certifi`는 SSL 인증서 번들 용도로만 씁니다.
- OpenAI 호환 Chat Completions API(`POST {BASE_URL}/chat/completions`)라면 어느 서비스든 사용할 수 있습니다.
- `git push`나 GitHub PR 생성 같은 원격 반영은 하지 않습니다. 초안 텍스트 출력까지만 합니다.

## 1. 설치

요구 사항: Python 3.10 이상, Git

```bash
git clone https://github.com/yun-lim/ai-commit-pr-generator.git
cd ai-commit-pr-generator
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # certifi (macOS python.org 설치판의 SSL 인증서 오류 방지)
```

## 2. 환경변수(API Key) 설정

API Key는 **환경변수로만** 읽습니다. 코드와 커밋에는 키를 넣지 않습니다.

| 환경변수 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `AI_API_KEY` | O | – | AI API 인증 키 |
| `AI_API_BASE_URL` | X | `https://ai-gateway.vercel.sh/v1` | OpenAI 호환 API 주소 |
| `AI_MODEL` | X | `openai/gpt-4.1-mini` | 기본 모델 (`--model`이 우선) |

```bash
# Vercel AI Gateway (기본값)
export AI_API_KEY="YOUR_KEY"

# OpenAI를 직접 쓰는 경우
export AI_API_KEY="sk-..."
export AI_API_BASE_URL="https://api.openai.com/v1"
export AI_MODEL="gpt-4.1-mini"
```

계속 쓸 경우 `~/.zshrc` 같은 셸 설정 파일에 넣으세요. `.env` 파일을 쓸 경우 `.gitignore`에 이미 포함되어 있습니다.

## 3. 사용법

**Git이 초기화된 프로젝트 루트 디렉토리**에서 실행합니다. 하위 폴더나 Git 저장소가 아닌 곳에서 실행하면 오류를 내고 종료합니다.
아래 예시의 `main.py` 경로는 이 도구를 설치한 위치로 바꿔 쓰세요. 예: `python ~/tools/ai-commit-pr-generator/main.py commit`

### 커밋 메시지 생성

```bash
git add -p                                  # 커밋할 변경을 stage (stage가 없으면 작업 트리 전체 사용)
python main.py commit
python main.py commit -c "로그인 실패 시 재시도 횟수 제한 요구사항 반영"   # 변경 이유 전달
python main.py commit --save commit_msg.txt && git commit -F commit_msg.txt  # 검토 후 적용
```

### PR 제목/본문 생성

```bash
python main.py pr                            # main...HEAD diff 기준
python main.py pr --base develop             # 기준 브랜치 변경
python main.py pr --save pr_body.md          # 본문만 저장 → gh pr create --body-file pr_body.md
```

브랜치에 커밋된 차이가 없으면 커밋 전 작업 트리 변경을 기준으로 초안을 만듭니다.

### 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `-m`, `--model` | `openai/gpt-4.1-mini` | 사용할 모델 |
| `-t`, `--temperature` | `0.2` | 0.0~2.0. 낮을수록 같은 diff에 일관된 결과 |
| `--max-tokens` | `700` | 응답 최대 토큰. 너무 작으면 JSON이 잘림 |
| `--timeout` | `30` | 요청 타임아웃(초) |
| `--retry` | 끔 | 형식 검증 실패 시 위반 내용을 알려주고 1회 재생성 (최대 2회 호출) |
| `-c`, `--context` | – | 변경 이유/요구사항을 프롬프트에 추가 |
| `--lang` | `ko` | 작성 언어 `ko` / `en` |
| `--save PATH` | – | 결과 파일 저장 (commit: 메시지 전체 / pr: 본문) |
| `--dry-run` | 끔 | API를 호출하지 않고 보낼 프롬프트만 출력 (비용 0) |
| `--safe-mode` | 끔 | 민감정보 마스킹 + 민감 파일 제외 + 파일/줄 수 제한 |
| `--max-files` / `--max-lines` | `10` / `200` | safe-mode 전송 한도 |
| `--max-diff-chars` | `12000` | 항상 적용되는 diff 최대 문자 수 (비용 보호) |
| `--base` (pr) | `main` | PR 비교 기준 브랜치 |

## 4. 출력 예시

진행 로그(`[INFO]` 등)는 stderr, 결과물은 stdout으로 출력됩니다. 결과물만 파일로 받으려면 `python main.py commit > msg.txt`처럼 쓰면 됩니다.
아래는 이 저장소를 만들면서 실제로 실행한 결과입니다.

### 커밋 메시지 (`python main.py commit --safe-mode -c "..."`)

```text
[INFO] 현재 브랜치: feature/ai-client
[INFO] Git status 수집 완료: 4개 파일 변경 감지
[INFO] Git diff 수집 완료: 200줄 (staged (git diff --cached))
[INFO] safe-mode ON: 파일 4/4개, 줄 159/200줄 전송, 마스킹 없음
[INFO] AI API 요청 중... (model=openai/gpt-4.1-mini, temperature=0.2, max_tokens=700)
[INFO] 응답 수신: prompt 2812 / completion 135 tokens
[INFO] AI API 호출 횟수: 1회
[DONE] 커밋 메시지 생성 완료

--- Commit Message ---
feat(safe_mode): 균등한 줄 예산 배분으로 큰 파일 독점 방지

- gitgen/safe_mode.py: 최대 파일 수/줄 수 제한 시 줄 예산을 파일 수로 균등 배분해 앞쪽 큰 파일이 예산을 독점하지 않도록 개선
- gitgen/cli.py: prepare_diff 함수 반환값에 DiffReport 추가 및 safe_mode 관련 출력 메시지 개선
- gitgen/prompts.py: diff 전송 범위를 명확히 알리는 describe_scope 함수 추가 및 커밋 메시지 작성 규칙 문구 보완
--------------------------------------------------
```

### PR 초안 (`python main.py pr --base main --safe-mode -c "..."`)

```text
[INFO] 현재 브랜치: feature/tests
[INFO] Git status 수집 완료: 15개 파일 변경 감지
[INFO] Git diff 수집 완료: 1383줄 (git diff main...HEAD)
[INFO] safe-mode ON: 파일 10/15개, 줄 183/1383줄 전송, 마스킹 SECRET 3건, API_KEY 2건, EMAIL 3건
[INFO] AI API 요청 중... (model=openai/gpt-4.1-mini, temperature=0.2, max_tokens=700)
[INFO] 응답 수신: prompt 2399 / completion 297 tokens
[INFO] AI API 호출 횟수: 1회
[DONE] PR 초안 생성 완료

--- PR Title ---
feat(cli): AI 기반 커밋 메시지 및 PR 초안 자동 생성 CLI 도구 추가
--------------------------------------------------

--- PR Body ---
## Why
- 커밋 메시지와 PR 초안을 자동으로 생성하여 개발자의 작업 효율을 높이기 위함
- 기존에 없던 AI 연동 기능과 git 변경사항 수집 및 검증 기능이 필요했음

## What
- gitgen 패키지에 AI 클라이언트(ai_client.py), CLI 진입점(cli.py), 초안 변환(drafts.py), 생성 및 검증(generator.py, validator.py) 모듈 추가
- git 변경사항 수집(git_collector.py) 및 민감정보 마스킹과 전송량 제한(safe_mode.py) 기능 구현
- 터미널 출력(output.py)과 프롬프트 설계(prompts.py) 모듈 추가
- 테스트 코드(tests/ 디렉터리) 추가로 각 모듈 기능 검증

## How to Test
- `python main.py commit` 또는 `python main.py pr` 명령어 실행하여 AI 기반 커밋 메시지 및 PR 초안 생성 확인
- 테스트 스위트 실행: `pytest tests/` 로 각 모듈별 유닛 테스트 통과 여부 확인
- 환경변수에 API 키와 베이스 URL 설정 후 정상적으로 AI API 호출되는지 검증
--------------------------------------------------
```

> 이 초안의 `pytest tests/`는 틀린 내용입니다. 이 프로젝트는 `unittest`를 씁니다. safe-mode로 테스트 파일 diff가 생략되자 AI가 흔한 명령을 추측한 것입니다.
> 그대로 쓰지 말고 `python -m unittest discover -s tests -t .`로 고쳐서 써야 합니다. 생성 결과는 정답이 아니고 **검토할 초안**입니다.

### 오류 / 예외 상황

```text
$ python main.py commit                      # 변경 사항 없음
[INFO] 변경 사항이 없습니다. 커밋 메시지를 생성하지 않고 종료합니다.

$ python main.py commit                      # API Key 미설정
[ERROR] AI_API_KEY 환경변수가 설정되지 않았습니다.
  예) export AI_API_KEY="YOUR_KEY"

$ AI_API_KEY=wrong-key python main.py commit # 인증 실패
[ERROR] 인증 실패(HTTP 401): AI_API_KEY 값이 올바른지, 권한이 있는지 확인하세요.
  서버 메시지: Authentication failed. ...

$ AI_API_BASE_URL=https://no-such-host.invalid/v1 python main.py commit   # 네트워크 오류
[ERROR] 네트워크 오류: [Errno 8] nodename nor servname provided, or not known (BASE_URL=...)

$ python main.py commit -t 5                 # 잘못된 파라미터
python main.py commit: error: argument -t/--temperature: temperature는 0.0~2.0 범위여야 합니다.
```

| 상황 | 메시지 / 처리 | 종료 코드 |
|---|---|---|
| 401 / 403 | 인증 실패: 키를 확인하라고 안내 + 서버 메시지 | 1 |
| 404 | 모델 이름 또는 BASE_URL 확인 안내 | 1 |
| 429 | 요청 한도 초과 안내 | 1 |
| 5xx | AI 서버 오류, 잠시 후 재시도 안내 | 1 |
| 네트워크 / 타임아웃 / SSL | 원인 + BASE_URL, `--timeout`, `certifi` 안내 | 1 |
| 빈 응답 / `finish_reason=length` | `--max-tokens` 늘리라는 안내 | 1 / 경고 |

## 5. 동작 원리

### Git 변경 사항 수집 (`gitgen/git_collector.py`)
- `git rev-parse --show-toplevel`로 프로젝트 루트에서 실행했는지 확인합니다.
- `git status --porcelain=v1 --branch`: 기계가 읽기 쉬운 형식으로 받아 브랜치와 파일 상태(수정/추가/삭제/신규)를 파싱합니다.
- commit: staged가 있으면 `git diff --cached`, 없으면 `git diff`와 untracked 파일(`git diff --no-index /dev/null <file>`)을 씁니다.
- pr: `git diff <base>...HEAD`로 브랜치가 갈라진 시점 이후의 변경만 사용합니다.

### 프롬프트 설계 (`gitgen/prompts.py`)
| 구성 요소 | 내용 | 목적 |
|---|---|---|
| system | 시니어 엔지니어 역할, "diff에 없는 내용 지어내지 않기", JSON만 출력 | 환각 억제, 파싱 안정성 |
| 규칙 | Conventional Commits type 목록, 50/72자, 불릿 1~3개·파일명 언급, PR Why/What/How to Test | 실무 양식 강제 |
| 맥락 | 브랜치, diff 기준, **diff 전송 범위**, 사용자 `--context`, status 파일 목록, diff | 변경 이유 반영, 생략된 부분 추측 방지 |
| 출력 스키마 | `{"title", "body"}` / `{"title", "why", "what", "how_to_test"}` | 템플릿은 코드가 렌더링해서 형식을 보장 |

**프롬프트 개선 기록**: 처음에는 safe-mode의 200줄 예산을 앞쪽 큰 파일 2개가 다 써서, AI가 나머지 4개 파일을 이름만 보고 추측했습니다(`drafts.py: 임시 데이터 처리 모듈`이라고 틀리게 씀). 불릿도 규칙(1~3개)과 달리 6개가 나왔습니다.
→ ① 줄 예산을 파일 수로 균등 배분 ② 프롬프트에 `[diff 전송 범위] 파일 4/4개, 줄 159/200줄`을 명시하고 "생략된 부분은 추측하지 말 것"을 추가 ③ 불릿 최대 3개·비슷한 파일은 묶기 규칙 추가. 이후 결과는 4개 파일을 모두 반영했고 불릿 3개로 정확해졌습니다.

### 파라미터
- `temperature`(기본 0.2): 다음 토큰을 고를 때의 무작위성입니다. 커밋 메시지는 사실 요약이므로 낮게 둡니다. 높이면 표현이 다양해지지만 diff에 없는 내용이 섞일 위험이 커집니다.
- `max_tokens`(기본 700): 응답 길이 상한이자 비용 상한입니다. 너무 작으면 JSON이 중간에 잘립니다(`finish_reason=length`이면 경고). 입력 토큰은 diff 크기가 결정하므로 `--max-diff-chars`와 safe-mode로 따로 제한합니다.
- `model`: 품질·속도·비용을 함께 결정합니다. 추론(thinking) 모델은 출력 토큰을 추론에 먼저 써서 빈 응답이 나올 수 있습니다.

### 검증과 후처리 (`gitgen/validator.py`, `gitgen/generator.py`)
| 대상 | 규칙 | 위반 시 |
|---|---|---|
| 커밋 제목 | 1줄, 50자 권장, 최대 72자, 끝 마침표·이모지 금지, `type(scope): 요약` | 72자 초과 → 단어 경계에서 자름 / 그 외 경고 |
| 커밋 본문 | 제목 다음 빈 줄, 불릿 1개 이상(3개 이하 권장), 파일명 언급 | 오류/경고 표시 |
| 모호한 제목 | `fix: update files`, `코드 수정` 등 | 오류 표시 (직접 수정 필요) |
| PR 제목 | 1줄, 최대 80자 | 80자 초과 → 자름 |
| PR 본문 | `## Why` / `## What` / `## How to Test` + 섹션마다 불릿 1개 이상 | 빠진 섹션에 "(작성 필요)" 불릿을 채워 템플릿 보장 |

기본은 **API 1회 호출 + 후처리**입니다. `--retry`를 주면 검증 실패 시 위반 목록을 AI에 다시 보내 1회만 재생성합니다(최대 2회 호출). 매 실행마다 `AI API 호출 횟수`를 로그로 출력합니다.

## 6. 주의사항 / 운영 관점

### 민감정보와 safe-mode
`git diff`에는 API Key, 비밀번호, 개인정보가 섞일 수 있고, 이 내용은 외부 AI 서버로 전송됩니다. 공개되면 안 되는 저장소에서는 `--safe-mode`를 쓰세요.

| 정책 | 기준 |
|---|---|
| (A) 마스킹 | `sk-…`, `AKIA…`, `ghp_…`, `AIza…`, `xox…`, `vck_…` 형태 키 → `[MASKED_API_KEY]`, `Bearer` 토큰, 이메일, 휴대폰 번호, PEM 개인키, `PASSWORD = "..."`처럼 이름에 key/secret/token/password가 들어간 변수의 값(6자 이상) |
| 민감 파일 제외 | `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `id_rsa*`, `*credentials*`, `*secret*` 파일은 diff에서 통째로 제외 |
| (B) 전송 제한 | 최대 10개 파일, 최대 200줄 (`--max-files`, `--max-lines`). 줄 예산은 파일마다 균등 배분 |
| 항상 적용 | diff 최대 12,000자 (`--max-diff-chars`) |

- 마스킹은 정규식 기반이라 완벽하지 않습니다. 보내기 전에 `--dry-run --safe-mode`로 실제 전송될 프롬프트를 확인할 수 있습니다.
- 전송량을 제한하면 AI가 못 본 파일이 생깁니다. 이 경우 프롬프트에 범위를 알려 추측을 막지만, 결과의 정확도는 떨어질 수 있습니다.

### 비용 / 요청 횟수
- `commit`과 `pr`은 각각 **API 1회 호출**이 기본입니다. `--retry`를 줘도 최대 2회입니다.
- 비용은 대부분 입력 토큰(diff 크기)에서 나옵니다. 큰 변경은 작게 나눠 커밋하고, lock 파일이나 빌드 산출물은 stage하지 마세요.
- 이 저장소 기준 1회 호출은 입력 약 1,000~4,000 토큰, 출력 약 100~300 토큰이었습니다.
- 자동 재시도는 하지 않습니다. 429(한도 초과)나 5xx가 나면 잠시 뒤 직접 다시 실행하세요.

### 결과물 사용
생성된 커밋/PR 문구는 최종 정답이 아닙니다. 사실과 다른 내용이나 테스트 방법이 있는지 검토한 뒤 적용하세요.

## 7. 개발

```bash
python -m unittest discover -s tests -t .    # 31개 테스트 (API 호출 없음, urlopen은 mock)
python main.py commit --dry-run              # 프롬프트만 확인
```

```text
.
├── main.py              # 실행 진입점
├── requirements.txt
├── gitgen/
│   ├── cli.py           # argparse 옵션, 전체 흐름, 오류 → 종료 코드
│   ├── git_collector.py # git status / git diff 수집·파싱
│   ├── safe_mode.py     # 마스킹, 민감 파일 제외, 파일/줄/문자 수 제한
│   ├── prompts.py       # system/규칙/맥락 프롬프트 구성
│   ├── ai_client.py     # REST 요청 구성, 응답 파싱, HTTP/네트워크 예외 처리
│   ├── drafts.py        # JSON 응답 → 커밋/PR 텍스트 렌더링
│   ├── validator.py     # 길이·템플릿·표현 규칙 검증, 후처리
│   ├── generator.py     # 호출 → 검증 → (재생성) → 후처리
│   └── output.py        # [INFO]/[ERROR] 로그, 구분선 출력
└── tests/
```
