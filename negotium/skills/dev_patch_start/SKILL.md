---
id: dev.patch_start
name: AI 개발 도우미 시작
description: 코드 수정 요청을 접수하고 저장소를 분석해 패치 계획을 만듭니다.
category: dev
executor: tool
tool: patch.start
required_permission: memory:write
risk: medium
inputs:
  - name: request
    type: string
    required: true
    description: 수정하고 싶은 내용 (예 - 로그인 버튼 문구 변경)
  - name: repo_id
    type: string
    required: false
    description: 대상 저장소 ID (기본 local)
---
코드 수정 요청을 AI 개발 도우미에 전달합니다. 저장소를 스캔하고 질문·패치 계획을 생성합니다.
