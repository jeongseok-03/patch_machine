---
id: dev.test_run
name: 테스트 실행
description: 워크스페이스에서 테스트 명령을 실행합니다. 기본은 dry-run으로 명령만 검증합니다.
category: dev
executor: tool
tool: test.run
required_permission: memory:write
risk: medium
inputs:
  - name: command
    type: string
    required: true
    description: "실행할 테스트 명령 (예: pytest -q)"
  - name: dry_run
    type: boolean
    required: false
    description: true면 명령을 실제로 실행하지 않고 검증만 합니다 (기본 true)
---
지정한 테스트 명령을 샌드박스 정책에 따라 실행합니다. 자가코딩 루프의 검증 단계에서 사용합니다.
