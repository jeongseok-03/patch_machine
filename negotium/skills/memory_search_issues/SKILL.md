---
id: memory.search_issues
name: 이슈 메모리 검색
description: 통합 이슈 메모리에서 관련 이슈/클러스터를 검색합니다.
category: memory
executor: tool
tool: memory.search_issues
required_permission: work:read
risk: low
inputs:
  - name: query
    type: string
    required: true
    description: 검색어
  - name: limit
    type: integer
    required: false
    description: 최대 결과 수 (기본 10)
---
이슈 메모리에서 query와 관련된 이슈 클러스터를 찾습니다. 패치 계획 수립 전 과거 사례를 조회할 때 사용합니다.
