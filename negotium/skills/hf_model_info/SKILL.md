---
id: hf.model_info
name: Hugging Face 모델 정보
description: 지정한 Hugging Face 모델의 메타데이터와 README 요약을 확인합니다.
category: admin
executor: tool
tool: hf.get_model_info
required_permission: work:read
risk: low
inputs:
  - name: model_id
    type: string
    required: true
    description: 모델 ID (예 - Qwen/Qwen3-4B)
---
모델 카드와 태그를 확인해 로컬 적용 후보를 검토합니다.
