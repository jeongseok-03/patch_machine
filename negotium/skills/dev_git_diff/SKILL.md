---
id: dev.git_diff
name: Git diff 조회
description: 현재 워크스페이스의 git diff를 조회합니다.
category: dev
executor: tool
tool: git.diff
required_permission: work:read
risk: low
inputs:
  - name: staged
    type: boolean
    required: false
    description: true면 스테이지된 변경만 표시
---
워크스페이스의 변경 사항을 git diff로 확인합니다. 패치 적용 전후 검토에 사용합니다.
