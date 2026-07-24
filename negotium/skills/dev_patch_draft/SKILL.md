---
id: dev.patch_draft
name: 패치 초안 작성
description: 승인된 패치 계획을 바탕으로 diff와 문서 초안을 생성합니다.
category: dev
executor: tool
tool: patch.draft_diff
required_permission: memory:write
risk: medium
inputs:
  - name: patch_run_id
    type: string
    required: true
    description: 패치 실행 ID
---
패치 실행 ID에 대해 diff·문서·테스트 초안을 생성합니다.
