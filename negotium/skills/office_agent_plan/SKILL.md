---
id: office.agent_plan
name: 실행 계획 생성
description: 업무 목표를 승인 가능한 실행 단계로 분해하는 계획을 만듭니다.
category: office
executor: tool
tool: agent.generate_plan
required_permission: memory:write
risk: low
inputs:
  - name: objective
    type: string
    required: true
    description: 달성하고 싶은 업무 목표
  - name: title
    type: string
    required: false
    description: 계획 제목
---
업무 목표를 바탕으로 에이전트 실행 계획을 생성합니다. 관리자 승인 후 실행할 수 있습니다.
