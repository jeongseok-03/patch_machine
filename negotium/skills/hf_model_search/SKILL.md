---
id: hf.model_search
name: Hugging Face 모델 검색
description: Hugging Face에서 로컬 LLM 후보 모델을 검색합니다.
category: admin
executor: tool
tool: hf.search_models
required_permission: work:read
risk: low
inputs:
  - name: query
    type: string
    required: false
    description: 검색어 (예 - qwen korean instruct)
  - name: limit
    type: number
    required: false
    description: 최대 결과 수
---
관리자가 로컬 LLM 후보를 찾을 때 사용합니다.
