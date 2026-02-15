# epub2kr

EPUB 파일을 레이아웃을 보존하면서 번역하는 CLI 도구입니다.

## 특징

- HTML/CSS 레이아웃을 완벽히 보존하면서 EPUB 번역
- 4가지 번역 서비스 지원: Google Translate (기본, 무료), DeepL, OpenAI, Ollama
- 한국어/일본어/중국어 번역 시 Noto 폰트 및 가독성 최적화 CSS 자동 적용
- SQLite 기반 번역 캐시로 중복 번역 방지
- 멀티스레드 병렬 번역으로 빠른 처리
- 원문+번역문을 함께 보여주는 바이링구얼 모드
- 목차(TOC) 자동 번역

## 설치

```bash
# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate

# 설치
pip install -e .
```

## 초기 설정

```bash
# 대화형 설정 마법사 (서비스, 언어, 모델 등 기본값 저장)
epub2kr --setup
```

설정은 `~/.epub2kr/config.json`에 저장되며, 이후 번역 시 기본값으로 사용됩니다.
CLI 옵션으로 지정하면 저장된 설정보다 우선합니다.

## 사용법

### 기본 사용 (Google Translate)

```bash
# 영어로 번역 (기본)
epub2kr book.epub

# 한국어로 번역
epub2kr book.epub -lo ko

# 출력 파일 직접 지정
epub2kr book.epub -o translated_book.epub -lo ko
```

### 번역 서비스 선택

```bash
# DeepL (API 키 필요)
epub2kr book.epub -s deepl --api-key YOUR_DEEPL_KEY -lo ja

# OpenAI (API 키 필요)
epub2kr book.epub -s openai --api-key sk-xxx --model gpt-4 -lo es

# Ollama (로컬 LLM)
epub2kr book.epub -s ollama --model llama2 -lo ko

# OpenAI 호환 API (커스텀 엔드포인트)
epub2kr book.epub -s openai --base-url http://localhost:8000/v1 --api-key dummy -lo zh
```

### 고급 옵션

```bash
# 바이링구얼 모드 (원문 + 번역문)
epub2kr book.epub --bilingual -lo ko

# 멀티스레드 (4스레드)
epub2kr book.epub -t 4 -lo ko

# 캐시 비활성화
epub2kr book.epub --no-cache -lo ko

# 소스 언어 직접 지정 (기본: auto)
epub2kr book.epub -li zh -lo en
```

### 폰트/줄간 설정 (CJK)

한국어, 일본어, 중국어로 번역할 때 폰트, 줄간, 문단 간격, 제목 폰트를 조정할 수 있습니다.

```bash
# 기본값 사용 (Noto Sans KR, 0.95em, 줄간 1.8, 문단간격 0.5em)
epub2kr book.epub -lo ko

# 폰트 크기/줄간 변경
epub2kr book.epub -lo ko --font-size 14px --line-height 2.0

# 커스텀 폰트 지정
epub2kr book.epub -lo ko --font-family '"NanumGothic", "Malgun Gothic", sans-serif'

# 제목 폰트를 별도로 지정 (본문: 고딕, 제목: 명조)
epub2kr book.epub -lo ko --heading-font '"Noto Serif KR", serif'

# 문단 간격 조정
epub2kr book.epub -lo ko --paragraph-spacing 1em
```

`epub2kr --setup`에서도 이 값들을 기본값으로 저장할 수 있습니다.

### 스타일 리스타일링 (epub2kr-restyle)

이미 번역된 EPUB의 폰트/줄간만 다시 조정할 때 사용합니다. 번역 없이 스타일만 변경합니다.

```bash
# 기본 사용 (새 파일로 저장: *.restyled.epub)
epub2kr-restyle book.ko.epub --font-size 1em --line-height 2.0

# 원본 덮어쓰기
epub2kr-restyle book.ko.epub --inplace --line-height 1.6

# 제목 폰트 + 문단 간격 조정
epub2kr-restyle book.ko.epub --heading-font '"Noto Serif KR", serif' --paragraph-spacing 1em

# 브라우저 GUI로 실시간 미리보기
epub2kr-restyle book.ko.epub --gui
```

`--gui` 옵션을 사용하면 브라우저에서 실시간으로 폰트, 줄간, 문단 간격을 조정하면서 미리보기를 확인할 수 있습니다.

## CLI 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `INPUT_FILE` | 입력 EPUB 파일 경로 (필수) | - |
| `-o, --output` | 출력 파일 경로 | `{입력파일명}.{대상언어}.epub` |
| `-s, --service` | 번역 서비스 (`google`, `deepl`, `openai`, `ollama`) | `google` |
| `-li, --source-lang` | 소스 언어 코드 | `auto` |
| `-lo, --target-lang` | 대상 언어 코드 | `en` |
| `-t, --threads` | 병렬 스레드 수 | `4` |
| `--no-cache` | 번역 캐시 비활성화 | `false` |
| `--bilingual` | 바이링구얼 출력 생성 | `false` |
| `--api-key` | 번역 서비스 API 키 | - |
| `--model` | 모델 이름 (OpenAI/Ollama용) | - |
| `--base-url` | 커스텀 API 베이스 URL | - |
| `--font-size` | CJK 폰트 크기 (예: `0.95em`, `14px`) | `0.95em` |
| `--line-height` | CJK 줄간 (예: `1.8`, `2.0`) | `1.8` |
| `--font-family` | CJK 본문 폰트 (미지정 시 언어별 자동 선택) | 자동 |
| `--heading-font` | CJK 제목 폰트 (미지정 시 본문과 동일) | 본문 동일 |
| `--paragraph-spacing` | 문단 간격 (예: `0.5em`, `1em`) | `0.5em` |
| `--setup` | 대화형 설정 마법사 실행 | - |

## 번역 서비스

| 서비스 | 인증 | 비용 | 비고 |
|--------|------|------|------|
| Google Translate | 불필요 | 무료 | 기본 서비스, 속도 제한 있음 |
| DeepL | API 키 | 유료/무료 티어 | 고품질 번역, `DEEPL_API_KEY` 환경변수 사용 가능 |
| OpenAI | API 키 | 유료 | GPT 모델 기반, `OPENAI_API_KEY` 환경변수 사용 가능 |
| Ollama | 불필요 | 무료 | 로컬 LLM, `localhost:11434`에서 Ollama 실행 필요 |

## CJK 폰트 최적화

한국어(`ko`), 일본어(`ja`), 중국어(`zh`, `zh-cn`, `zh-tw`)로 번역 시 EPUB에 CSS 스타일시트가 자동 삽입됩니다.

### 기본값

| 항목 | 기본값 | 설명 |
|------|--------|------|
| 폰트 크기 | `0.95em` | 원문 대비 약 5% 축소 |
| 줄간 | `1.8` | CJK 가독성 최적화 |
| 문단 간격 | `0.5em` | `<p>` 태그 하단 마진 |
| 본문 폰트 | 언어별 자동 선택 | 아래 표 참고 |
| 제목 폰트 | 본문과 동일 | 별도 지정 시 `h1`~`h6`에 적용 |

### 언어별 기본 폰트 스택

| 언어 | 기본 font-family |
|------|-----------------|
| 한국어 (`ko`) | Noto Sans KR, Apple SD Gothic Neo, Malgun Gothic |
| 일본어 (`ja`) | Noto Sans JP, Hiragino Sans, Yu Gothic |
| 중국어 간체 (`zh`, `zh-cn`) | Noto Sans SC, PingFang SC, Microsoft YaHei |
| 중국어 번체 (`zh-tw`) | Noto Sans TC, PingFang TC, Microsoft JhengHei |

### 커스터마이즈

세 가지 방법으로 변경 가능:

1. **CLI 옵션**: `--font-size`, `--line-height`, `--font-family`, `--heading-font`, `--paragraph-spacing`
2. **설정 마법사**: `epub2kr --setup`에서 CJK Font Settings 섹션
3. **설정 파일**: `~/.epub2kr/config.json` 직접 편집
4. **리스타일 도구**: `epub2kr-restyle` — 번역 없이 스타일만 재조정
5. **GUI 미리보기**: `epub2kr-restyle --gui` — 브라우저에서 실시간 조정

```json
{
  "font_size": "0.9em",
  "line_height": "2.0",
  "paragraph_spacing": "0.8em",
  "font_family": "\"NanumGothic\", \"Malgun Gothic\", sans-serif",
  "heading_font_family": "\"Noto Serif KR\", serif"
}
```

EPUB 리더에 지정한 폰트가 설치되어 있으면 자동으로 적용됩니다.

## 캐시

번역 결과는 `~/.epub2kr/cache.db` (SQLite)에 자동 캐싱됩니다. 동일한 텍스트를 다시 번역할 때 API 호출 없이 캐시에서 즉시 반환합니다.

- 캐시 키: `SHA-256(원문) + 소스언어 + 대상언어 + 서비스명`
- `--no-cache` 옵션으로 비활성화 가능

## 프로젝트 구조

```
src/epub2kr/
├── __init__.py          # 패키지 초기화
├── cli.py               # Click 기반 CLI 인터페이스
├── restyle.py           # epub2kr-restyle CLI (스타일 재조정)
├── gui.py               # 브라우저 기반 restyle 미리보기 GUI
├── translator.py        # 번역 파이프라인 오케스트레이터
├── epub_parser.py       # EPUB 읽기/쓰기 (ebooklib)
├── text_extractor.py    # XHTML 텍스트 추출/교체 (lxml)
├── cache.py             # SQLite 번역 캐시
└── services/
    ├── __init__.py      # 서비스 팩토리
    ├── base.py          # 추상 베이스 클래스
    ├── google.py        # Google Translate (무료 웹 API)
    ├── deepl.py         # DeepL API
    ├── openai_service.py # OpenAI API
    └── ollama.py        # Ollama (로컬 LLM)
```

## 라이선스

이 프로젝트는 [GNU Affero General Public License v3.0](LICENSE)에 따라 배포됩니다. 자세한 내용은 [NOTICE](NOTICE) 파일을 참조하세요.
