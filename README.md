# PromptZip V44 + PromptCraft

V44는 새로운 기능을 추가하지 않고, 고객이 PromptZip과 PromptCraft의 차이를 더 쉽게 이해하도록 선택 안내 UI를 정리한 버전입니다.

## 실행

압축을 푼 뒤 아래 파일을 더블클릭하세요.

```text
START_HERE_WINDOWS.bat
```

브라우저 주소:

```text
http://127.0.0.1:8816
```

정상 확인 주소:

```text
http://127.0.0.1:8816/healthz
```

관리자 화면:

```text
http://127.0.0.1:8816/admin
```

관리자 비밀번호:

```text
admin1234
```

## V44 디자인 보정 방향

- 문장 안에 PromptZip / PromptCraft 배지를 끼워 넣던 구조 제거
- 고객이 바로 이해하도록 두 기능을 카드형 선택 안내로 분리
- PromptZip은 파란 Zip 카드, PromptCraft는 민트 Craft 카드로 표시
- 4단계 흐름의 1번 목적 선택 카드 가독성 개선
- 무료 체험 영역의 기능 선택 안내를 더 명확하게 정리
- FAQ에서도 두 기능 차이를 비교 카드로 표시
- 기존 압축, 질문 생성, 엔진별 과금 옵션 기능은 그대로 유지

## 배포

Render/Railway 배포를 위해 `PORT` 환경변수를 자동으로 읽습니다. 로컬에서는 기본 8816 포트를 사용합니다.
