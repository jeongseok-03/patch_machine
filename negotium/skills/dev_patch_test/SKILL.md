---
id: dev.patch_test
name: 패치 테스트 실행
description: 패치 후 테스트를 dry-run 또는 실제 실행합니다 (기본 dry-run).
category: dev
executor: tool
tool: patch.run_tests
required_permission: memory:write
risk: medium
inputs:
  - name: command
    type: string
    required: false
    description: "실행할 테스트 명령 (예: python -m pytest -q)"
  - name: dry_run
    type: boolean
    required: false
    description: true면 명령만 검증 (기본 true)
---
패치 검증을 위해 테스트 명령을 실행합니다. 기본값은 dry-run입니다.
