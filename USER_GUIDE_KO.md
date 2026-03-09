# 📖 AIAutoMouse 사용자 가이드

> **버전**: 0.1.0 · **지원 환경**: Windows 10 / Windows 11

---

## 목차

1. [👋 AIAutoMouse 소개](#-aiautomouse-소개)
2. [✅ 설치 전 준비사항](#-설치-전-준비사항)
3. [📥 설치 방법 (Step-by-Step)](#-설치-방법-step-by-step)
4. [🚀 실행 및 기본 사용법](#-실행-및-기본-사용법)
5. [🖥️ GUI 프로그램 사용법](#️-gui-프로그램-사용법)
6. [⚙️ 설정 파일 안내](#️-설정-파일-안내)
7. [💡 자주 묻는 질문 및 팁](#-자주-묻는-질문-및-팁)

---

## 👋 AIAutoMouse 소개

**AIAutoMouse**는 마우스 클릭, 키보드 입력, 화면 읽기를 AI가 대신 해 주는 **똑똑한 윈도우 데스크톱 자동화 비서**입니다.
사람이 반복적으로 하는 작업을 YAML 또는 JSON으로 작성된 **"매크로"** 파일에 기록해 두면, 프로그램이 정확하게 그 작업을 자동으로 수행합니다.

### 🌟 주요 기능

| 기능 | 설명 |
|------|------|
| 🔍 **OCR (글자 인식)** | 화면에 보이는 텍스트를 읽어서 특정 글자의 위치를 찾습니다 (한국어·영어 지원) |
| 🖼️ **이미지 템플릿 매칭** | 미리 캡처해 둔 이미지와 같은 모양을 화면에서 찾아 클릭합니다 |
| 🪟 **Windows UI 자동화 (UIA)** | 버튼, 입력 칸 등 윈도우 UI 요소를 직접 인식하고 제어합니다 |
| 🌐 **웹 브라우저 제어** | Chrome/Edge 브라우저의 웹 페이지 요소를 자동으로 클릭·입력합니다 |
| ⌨️ **단축키 서비스** | 지정한 단축키를 누르면 매크로가 자동 실행됩니다 |
| 🖥️ **GUI 관리 화면** | 코드를 몰라도 시각적으로 매크로를 관리·실행할 수 있습니다 |
| 🛑 **긴급 정지** | 실행 중 `Ctrl+Alt+Pause`를 누르면 즉시 중단됩니다 |

---

## ✅ 설치 전 준비사항

시작하기 전에 아래 항목을 확인해 주세요.

### 1. 지원 운영체제

- ✅ **Windows 10** (64비트)
- ✅ **Windows 11** (64비트)
- ❌ macOS, Linux는 지원하지 않습니다

### 2. Python 설치 (필수)

AIAutoMouse를 사용하려면 **Python 3.10 이상 ~ 3.12 이하** 버전이 필요합니다.

#### Python이 이미 설치되어 있는지 확인하기

1. 키보드에서 `Win + R` 키를 눌러 "실행" 창을 엽니다
2. `cmd`를 입력하고 엔터를 누릅니다
3. 열린 검은 화면(명령 프롬프트)에 아래 명령어를 복사해서 붙여넣고 엔터를 누릅니다:

```
python --version
```

4. `Python 3.10.x` ~ `Python 3.12.x` 와 같은 결과가 나오면 준비 완료입니다 ✅

#### Python이 없거나 버전이 맞지 않다면

1. 🌐 [Python 공식 다운로드 페이지](https://www.python.org/downloads/)에 접속합니다
2. **Python 3.10** 이상, **3.12** 이하 버전의 **"Windows installer (64-bit)"** 를 다운로드합니다
3. 설치 프로그램을 실행합니다

> ⚠️ **매우 중요!** 설치 첫 화면에서 **"Add Python to PATH"** (또는 "Add python.exe to PATH") 체크박스에 반드시 ✅ 체크해 주세요. 이걸 빠뜨리면 나중에 명령어가 작동하지 않습니다!

4. `Install Now`를 클릭하여 설치를 완료합니다

### 3. Git 설치 (선택사항)

소스 코드를 `git clone`으로 내려받으려면 Git이 필요합니다. 🌐 [Git 다운로드 페이지](https://git-scm.com/download/win)에서 설치할 수 있습니다.

> 💡 Git이 어렵게 느껴지시면 ZIP 파일로 다운로드하셔도 됩니다! (아래 설치 방법 참고)

---

## 📥 설치 방법 (Step-by-Step)

차근차근 따라해 보세요. 모든 명령어는 **복사(Ctrl+C) → 붙여넣기(Ctrl+V)** 하시면 됩니다!

### Step 1️⃣ 터미널(명령 프롬프트) 열기

1. 키보드에서 `Win` 키를 누릅니다
2. **"cmd"** 또는 **"명령 프롬프트"** 를 검색합니다
3. 검색 결과에서 **"명령 프롬프트"** 를 클릭합니다

> 💡 **Windows Terminal** 이나 **PowerShell** 을 사용해도 됩니다!

### Step 2️⃣ 소스 코드 다운로드

**방법 A — Git으로 내려받기** (Git이 설치되어 있는 경우):

```
git clone https://github.com/your-org/aiautomouse.git
cd aiautomouse
```

**방법 B — ZIP 파일로 다운로드** (Git이 없는 경우):

1. 프로젝트의 GitHub 페이지에서 **Code → Download ZIP**을 클릭합니다
2. 다운로드한 ZIP 파일의 압축을 풀어줍니다 (예: `C:\coding\aiautomouse`)
3. 명령 프롬프트에서 해당 폴더로 이동합니다:

```
cd C:\coding\aiautomouse
```

### Step 3️⃣ 가상환경 만들기 및 접속

가상환경(venv)은 이 프로그램 전용의 깨끗한 작업 공간이라고 생각하시면 됩니다.

```
python -m venv venv
```

잠시 기다리면 `venv` 폴더가 만들어집니다. 이제 가상환경을 **활성화(켜기)** 합니다:

```
venv\Scripts\activate
```

> ✅ **성공 확인**: 명령 줄 맨 앞에 `(venv)` 라는 글자가 표시되면 성공입니다!
>
> ```
> (venv) C:\coding\aiautomouse>
> ```

> ⚠️ **터미널을 닫았다가 다시 열 때마다** `venv\Scripts\activate`를 다시 입력해야 합니다!

### Step 4️⃣ 필수 패키지 설치

아래 명령어로 프로그램에 필요한 모든 라이브러리를 설치합니다:

```
pip install -r requirements.txt
```

> ⏱️ 이 과정은 인터넷 속도에 따라 5~15분 정도 걸릴 수 있습니다. 끝날 때까지 기다려 주세요!

### Step 5️⃣ 프로그램 설치 (매우 중요! ⭐)

> 🚨 **이 단계를 건너뛰면 `aiautomouse` 명령어가 작동하지 않습니다!**

```
pip install -e .
```

이 명령어는 AIAutoMouse를 "편집 가능 모드"로 설치합니다. 이렇게 해야 터미널에서 `aiautomouse`라는 명령어를 바로 사용할 수 있게 됩니다.

> ✅ **확인 방법**: 설치 후 아래 명령어를 입력해 보세요:
>
> ```
> aiautomouse --help
> ```
>
> 사용법 안내 메시지가 출력되면 성공입니다! 🎉

### Step 6️⃣ 브라우저 자동화 설치 (Playwright)

웹 브라우저 자동화 기능을 사용하려면 Playwright 브라우저를 추가로 설치해야 합니다:

```
playwright install chromium
```

> 💡 이 단계는 웹 브라우저 자동화가 필요한 경우에만 필수입니다. 데스크톱 앱만 자동화한다면 건너뛰어도 됩니다.

---

## 🚀 실행 및 기본 사용법

> ⚠️ 모든 명령어는 **가상환경이 활성화된 상태** `(venv)`에서 실행해야 합니다!

### 1. 🩺 상태 점검하기 — `aiautomouse doctor`

프로그램이 정상적으로 설치되었는지 확인하는 **진단 명령어** 입니다. 가장 먼저 실행해 보세요!

```
aiautomouse doctor
```

> 💡 위 명령이 안 되면 `python -m aiautomouse doctor` 를 대신 사용해 보세요.

실행하면 아래와 같은 JSON 형식의 진단 결과가 출력됩니다:

```json
{
  "settings_path": "C:\\coding\\aiautomouse\\config\\app.yaml",
  "dpi_mode": "per_monitor_v2",
  "capture_backend": "mss",
  "emergency_stop_hotkey": "Ctrl+Alt+Pause",
  "providers": {
    "browser_cdp": true,
    "windows_uia": true,
    "ocr": true,
    "template_match": true
  }
}
```

#### 📋 진단 결과 확인 포인트

| 항목 | 의미 | ✅ 정상 |
|------|------|---------|
| `browser_cdp` | 웹 브라우저 제어 기능 | `true` |
| `windows_uia` | 윈도우 UI 인식 기능 | `true` |
| `ocr` | 화면 글자 읽기 기능 | `true` |
| `template_match` | 이미지로 위치 찾기 기능 | `true` |

> 💡 `browser_cdp`이 `false`로 나와도 괜찮습니다! 웹 브라우저 자동화를 쓰지 않는다면 문제 없습니다.
> `windows_uia`와 `template_match`이 `true`이면 대부분의 데스크톱 자동화를 사용할 수 있습니다.

### 2. 🖥️ GUI 프로그램 띄우기 — `aiautomouse gui`

코드를 잘 모르셔도 시각적인 화면에서 매크로를 관리하고 실행할 수 있습니다:

```
aiautomouse gui
```

> 💡 또는 `python -m aiautomouse gui` 로도 실행할 수 있습니다.

그래픽 화면이 열리면 아래 5개의 탭을 사용할 수 있습니다:

| 탭 이름 | 설명 |
|---------|------|
| 📝 **Snippets** | 자주 쓰는 텍스트 조각을 저장·관리합니다 |
| 🖼️ **Templates** | 이미지 템플릿을 가져오거나 화면 캡처로 만들 수 있습니다 |
| ⚡ **Macros** | 매크로 파일을 편집·저장·단축키 등록을 합니다 |
| 📊 **Run / Logs** | 매크로를 실행하고 실행 기록·로그를 확인합니다 |
| ⚙️ **Settings** | OCR 설정, 브라우저 URL, 긴급 정지 단축키 등을 변경합니다 |

### 3. ▶️ 매크로 실행하기 — `aiautomouse run`

준비된 샘플 매크로를 터미널에서 바로 실행하는 방법입니다.

#### 미리보기 모드 (Dry-Run — 실제 클릭 없이 테스트)

```
aiautomouse run macros/samples/calculator_click_button.yaml --mode dry-run
```

> 💡 `--mode dry-run`으로 실행하면 실제 마우스 클릭이나 키 입력이 **일어나지 않습니다**. 매크로가 정상적으로 작동하는지 안전하게 확인할 수 있어요!

#### 실제 실행 모드

```
aiautomouse run macros/samples/calculator_click_button.yaml --mode execute
```

> 🛑 **긴급 정지**: 매크로 실행 중에 `Ctrl + Alt + Pause` 키를 누르면 즉시 중단됩니다!

#### 📂 포함된 샘플 매크로 목록

```
macros/samples/
├── browser_playwright_data_url.json    ← 브라우저 제어 예제
├── browser_search_cdp.yaml            ← 브라우저 검색 자동화
├── calculator_click_button.yaml       ← 계산기 버튼 클릭
├── conditional_submit.json            ← 조건부 버튼 클릭
├── focus_and_paste.json               ← 창 포커스 후 붙여넣기
├── image_click_retry.json             ← 이미지 찾아 클릭 (재시도)
├── notepad_insert_snippet.yaml        ← 메모장 텍스트 삽입
├── screen_find_text_ocr.yaml          ← 화면 OCR 텍스트 검색
└── upload_and_submit.json             ← 파일 업로드 후 제출
```

### 4. 🤖 자연어로 매크로 생성하기 — `aiautomouse author`

한국어나 영어로 자동화하고 싶은 작업을 설명하면, AI가 매크로 JSON을 자동으로 만들어 줍니다:

```
aiautomouse author --text "메모장을 열고 '안녕하세요'를 입력한다" --output my_macro.json
```

### 5. ⌨️ 단축키 서비스 시작 — `aiautomouse serve`

등록된 단축키를 백그라운드에서 감시하면서, 단축키를 누르면 매크로를 자동 실행합니다:

```
aiautomouse serve
```

> 💡 종료하려면 `Ctrl + C`를 누르세요.

---

## ⚙️ 설정 파일 안내

프로그램의 모든 설정은 `config/app.yaml` 파일에서 관리합니다.
GUI의 **Settings** 탭에서도 동일하게 변경할 수 있습니다.

### 주요 설정 항목

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `emergency_stop_hotkey` | `Ctrl+Alt+Pause` | 긴급 정지 단축키 |
| `provider_find_timeout_ms` | `30000` (30초) | 대상 탐색 시 최대 대기 시간 (밀리초) |
| `ocr.backends` | `windows, tesseract, easyocr` | 사용할 OCR 엔진 목록 |
| `ocr.easyocr_languages` | `en, ko` | EasyOCR 인식 언어 |
| `capture.backend` | `mss` | 화면 캡처 방식 (`mss` 또는 `dxcam`) |
| `browser.launch_on_demand` | `true` | 브라우저를 필요할 때 자동 실행 |
| `overlay.enabled` | `true` | 디버그 오버레이 표시 여부 |
| `ui.default_macro_mode` | `dry-run` | GUI에서 매크로 기본 실행 모드 |

### 폴더 구조 안내

| 폴더 | 역할 |
|------|------|
| `assets/snippets/` | 텍스트 스니펫 저장 폴더 |
| `assets/templates/` | 이미지 템플릿 저장 폴더 |
| `macros/samples/` | 매크로 파일 저장 폴더 |
| `config/` | 설정 파일 폴더 (`app.yaml`, `hotkeys.yaml`) |
| `logs/` | 로그 파일 폴더 |
| `logs/runs/` | 매크로 실행 결과 및 스크린샷 저장 폴더 |
| `schemas/` | 매크로 JSON 스키마 파일 |

---

## 💡 자주 묻는 질문 및 팁

### ❓ "명령어를 찾을 수 없다고 나와요!"

**원인 1 — 가상환경이 꺼져 있습니다**

명령 줄 맨 앞에 `(venv)`가 보이는지 확인해 보세요. 없다면 가상환경을 다시 켜주세요:

```
venv\Scripts\activate
```

**원인 2 — `pip install -e .`를 하지 않았습니다**

가상환경을 켠 상태에서 반드시 아래 명령을 실행해야 합니다:

```
pip install -e .
```

**원인 3 — Python이 PATH에 등록되지 않았습니다**

Python을 재설치할 때 **"Add Python to PATH"** 에 체크한 후 설치해 주세요.

> 💡 그래도 안 된다면, `aiautomouse` 대신 `python -m aiautomouse`를 사용해 보세요!

---

### ❓ "매크로를 실행했는데 아무것도 안 돼요!"

1. **`--mode dry-run`으로 실행하고 계시진 않나요?**
   Dry-Run 모드에서는 실제 마우스/키보드 동작이 일어나지 않습니다. `--mode execute`로 실행해 보세요.

2. **대상 창(프로그램)이 열려 있나요?**
   자동화할 프로그램(예: 계산기, 메모장, 브라우저)이 미리 열려 있어야 합니다.

3. **로그를 확인해 보세요!**
   `logs/runs/` 폴더에 실행 결과가 저장됩니다. 어떤 단계에서 실패했는지 확인할 수 있어요.

---

### ❓ "OCR이 한국어를 인식 못 해요!"

`config/app.yaml` 파일에서 `easyocr_languages`에 `ko`가 포함되어 있는지 확인해 주세요:

```yaml
ocr:
  easyocr_languages:
    - en
    - ko
```

---

### ❓ "브라우저 자동화가 안 돼요!"

`playwright install chromium` 명령어를 실행했는지 확인해 주세요. 그리고 `aiautomouse doctor`를 실행해서 `browser_cdp`이 `true`인지 확인해 보세요.

---

### ❓ "실행 중 갑자기 멈추지 않아요!"

키보드에서 `Ctrl + Alt + Pause`를 누르면 실행 중인 모든 매크로가 즉시 중단됩니다.
이 단축키는 `config/app.yaml`의 `emergency_stop_hotkey` 항목에서 변경할 수 있습니다.

---

### 🔍 디버깅 로그 확인 방법

매크로를 실행할 때마다 `logs/runs/` 폴더에 **실행 기록**이 자동으로 저장됩니다:

| 파일 | 내용 |
|------|------|
| `events.jsonl` | 매크로의 모든 실행 단계 이벤트 로그 |
| `summary.json` | 실행 결과 요약 (성공/실패, 소요 시간 등) |
| `screenshots/` | 실행 중 캡처한 스크린샷 이미지 |
| `debug/` | OCR 인식 결과, 이미지 매칭 히트맵 등 디버깅 자료 |

> 💡 GUI의 **Run / Logs** 탭에서도 같은 내용을 시각적으로 확인할 수 있습니다.

---

### 📝 명령어 요약 카드

| 하고 싶은 것 | 명령어 |
|-------------|--------|
| 🩺 상태 점검 | `aiautomouse doctor` |
| 🖥️ GUI 실행 | `aiautomouse gui` |
| ▶️ 매크로 미리보기 | `aiautomouse run 매크로.yaml --mode dry-run` |
| ▶️ 매크로 실행 | `aiautomouse run 매크로.yaml --mode execute` |
| 🤖 매크로 자동 생성 | `aiautomouse author --text "설명" --output 파일.json` |
| ⌨️ 단축키 서비스 | `aiautomouse serve` |
| 🛑 긴급 정지 | `Ctrl + Alt + Pause` |
| 🔧 도움말 | `aiautomouse --help` |

---

> 🎉 **축하합니다!** 여기까지 따라오셨다면 AIAutoMouse를 사용할 준비가 모두 끝났습니다.
> 궁금한 점이 있으시면 샘플 매크로를 하나씩 실행해 보면서 익혀 보세요!
