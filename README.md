# 쿠팡 발주 모니터링 → 노션 알림

쿠팡 공급업체 포털의 발주리스트를 **1시간마다** 자동으로 확인하여,  
새로운 발주가 생기면 노션 캘린더에 **"로켓 발주를 확인하세요❤️"** 알림을 추가합니다.

---

## ⚠️ 중요: 2단계 인증 문제

쿠팡 공급업체 포털은 **로그인 시 2단계 인증(SMS)** 이 필요합니다.  
GitHub Actions 환경에서는 SMS를 받을 수 없으므로, **세션 쿠키 방식**을 사용해야 합니다.

### 세션 쿠키 추출 방법

1. PC의 Chrome 브라우저에서 쿠팡 공급업체 포털에 로그인합니다.
2. `F12` → **Application** → **Cookies** → `https://supplier.coupang.com` 선택
3. `PCID`, `x-coupang-accept-language`, `sid` 등 주요 쿠키 값을 복사합니다.
4. GitHub Secrets에 `COUPANG_COOKIES` 이름으로 JSON 형식으로 저장합니다.

> 세션 쿠키는 보통 **30일~90일** 유효합니다. 만료되면 재로그인 후 갱신이 필요합니다.

---

## 설정 방법

### 1단계: GitHub 저장소 생성

1. GitHub에서 **새 Private 저장소** 생성 (예: `coupang-monitor`)
2. 이 파일들을 저장소에 업로드합니다:
   - `monitor.py`
   - `.github/workflows/monitor.yml`

### 2단계: GitHub Secrets 등록

저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret 이름 | 값 |
|-------------|-----|
| `COUPANG_ID` | `ilsanghabo11` |
| `COUPANG_PW` | 쿠팡 비밀번호 |
| `NOTION_TOKEN` | `나중에 Secrets 설정에서 입력하세요` |
| `NOTION_DB_ID` | `310c081d6cc98053b868e6db557854ad` |
| `NOTION_USER_ID` | `33f2349e-2248-466a-8ef6-ab57505ba52f` |

### 3단계: 워크플로우 활성화

저장소 → **Actions** 탭 → **쿠팡 발주 모니터링** → **Enable workflow**

### 4단계: 수동 테스트 실행

Actions 탭 → **쿠팡 발주 모니터링** → **Run workflow** 버튼 클릭

---

## 파일 구조

```
coupang-monitor/
├── monitor.py                        # 메인 모니터링 스크립트
├── .github/
│   └── workflows/
│       └── monitor.yml               # GitHub Actions 워크플로우
└── README.md
```

---

## 동작 방식

1. GitHub Actions가 **매 정시**에 자동 실행됩니다.
2. 쿠팡 공급업체 포털에 로그인하여 발주리스트를 조회합니다.
3. 이전 실행 시 저장된 발주번호와 비교합니다.
4. **새 발주번호가 있으면** 노션 캘린더에 항목을 추가합니다.
5. 노션 담당자(클레어)에게 **수신함 알림**이 전송됩니다.

---

## 주의사항

- GitHub Actions 무료 플랜은 월 **2,000분** 제공됩니다. 1시간마다 실행 시 월 약 **720분** 사용됩니다.
- 쿠팡 세션 쿠키가 만료되면 크롤링이 실패합니다. 이 경우 쿠키를 재발급하여 Secrets를 업데이트하세요.
