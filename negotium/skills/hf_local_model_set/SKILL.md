---
id: hf.local_model_set
name: 로컬 LLM 모델 지정
description: 관리자 권한으로 Negotium의 로컬 LLM 모델을 지정합니다.
category: admin
executor: tool
tool: hf.set_local_model
required_permission: admin:local_llm
risk: medium
inputs:
  - name: model_id
    type: string
    required: true
    description: 적용할 모델 ID (예 - Qwen/Qwen3-4B)
---
민감 정보 처리를 로컬 에이전트 서버로 돌릴 때 사용할 모델을 설정합니다.
