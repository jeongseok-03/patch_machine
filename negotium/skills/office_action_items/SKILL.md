---
id: office.action_items
name: 액션 아이템 추출
description: 회의·대화·메모에서 실행 가능한 액션 아이템과 담당/기한을 추출합니다.
category: office
executor: prompt
required_permission: llm:chat
risk: low
output_format: markdown
output_folder: documents
task: document_generation
inputs:
  - name: source_text
    type: string
    required: true
    description: 액션을 추출할 회의/대화/메모 원문
  - name: owner_hint
    type: string
    required: false
    description: 담당자 후보나 팀 정보
---
다음 내용에서 실행 가능한 액션 아이템을 추출하세요.

원문:
{{ source_text }}

{% if owner_hint %}담당 후보/팀: {{ owner_hint }}{% endif %}

작성 지침:
- 각 액션을 `- [ ] 액션 (담당: …, 기한: …)` 형태의 체크리스트로 정리합니다.
- 담당/기한이 원문에 없으면 `미지정`으로 표기합니다.
- 의사결정이 필요한 항목은 별도 "결정 필요" 섹션으로 분리합니다.
- 출력의 첫 줄에 `<!-- negotium:format=markdown -->`를 넣고 본문을 작성하세요.
