---
id: office.summarize
name: 내용 요약
description: 회의록·메일·문서·메모 등 긴 내용을 핵심만 간결히 요약합니다.
category: office
executor: prompt
required_permission: llm:chat
risk: low
output_format: text
output_folder: documents
task: document_generation
inputs:
  - name: source_text
    type: string
    required: true
    description: 요약할 원문(회의록, 메일, 보고 내용 등)
  - name: focus
    type: string
    required: false
    description: 특히 강조할 관점이나 질문
---
다음 내용을 회사 업무용으로 간결하게 요약하세요.

원문:
{{ source_text }}

{% if focus %}요약 관점: {{ focus }}{% endif %}

작성 지침:
- 3~6개의 핵심 불릿으로 요약합니다.
- 결정 사항과 후속 액션(담당자가 있으면 함께)을 분리해 정리합니다.
- 불확실하거나 누락된 정보가 있으면 마지막에 "확인 필요"로 표시합니다.
- 출력의 첫 줄에 `<!-- negotium:format=text -->`를 넣고 본문을 작성하세요.
