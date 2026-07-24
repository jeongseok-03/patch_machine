---
id: dev.patch_pr
name: PR 초안 작성
description: 패치 실행 결과로 Pull Request 초안을 작성합니다.
category: dev
executor: tool
tool: patch.draft_pr
required_permission: memory:write
risk: medium
inputs:
  - name: patch_run_id
    type: string
    required: true
    description: 패치 실행 ID
  - name: branch_name
    type: string
    required: false
    description: PR 대상 브랜치 이름
---
패치 실행에 대한 PR 초안을 생성합니다. 머지는 관리자 승인 후 진행합니다.
