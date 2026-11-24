# TokenView

Token Monitoring Widget for Claude Code — Windows 작업표시줄(트레이)에서 Claude 사용량을 확인하는 작은 프로그램.

- 아이콘 숫자: 5시간 세션 사용률(%). 배경색 60% 미만 초록 · 85% 미만 노랑 · 그 이상 빨강
- 아이콘 아래 흰 막대: 주간(7일) 사용률
- 마우스를 올리면 세션·주간 수치와 리셋까지 남은 시간, 클릭하면 메뉴(새로고침, 사용량 페이지, Windows 시작 시 자동 실행)
- 80%·95% 도달 시 Windows 알림, 5분마다 갱신
- Claude에는 '일일' 한도가 따로 없어 5시간 세션 한도와 주간 한도를 보여준다.

## 사용법

1. PC에 Python 3와 Claude Code CLI가 있고, Claude Code에 구독 계정으로 한 번 로그인되어 있어야 한다.
2. `실행.bat` 더블클릭 (처음 한 번 pystray·pillow·requests 설치). 아이콘이 안 보이면 시계 옆 `^`(숨겨진 아이콘)에서 끌어다 놓는다.
3. 콘솔 창 없는 단독 실행 파일이 필요하면 `exe만들기.bat` → `dist\ClaudeUsageTray.exe`.

## 동작 원리와 주의

- Claude Code가 저장한 로그인 토큰(`%USERPROFILE%\.claude\.credentials.json`)으로 `https://api.anthropic.com/api/oauth/usage`(Claude Code의 사용량 조회와 같은 엔드포인트)를 조회한다. 토큰은 이 PC 안에서만 읽고 위 주소로만 보낸다.
- 비공식 엔드포인트라 Anthropic이 바꾸면 멈출 수 있다.
- 토큰이 만료되면 아이콘에 `!`가 뜬다. Claude Code를 한 번 실행하면 갱신된다.
- claude.ai, Claude Desktop, Claude Code는 같은 한도를 공유하므로 채팅 사용량도 반영된다.
