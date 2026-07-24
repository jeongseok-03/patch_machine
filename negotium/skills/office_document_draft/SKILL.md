---
id: office.document_draft
name: 문서 초안 작성
description: 제목과 원문/메모를 받아 회사 업무용 문서를 작성합니다. 출력 형식은 내용에 맞춰 AI가 선택합니다.
category: office
executor: prompt
required_permission: documents:write
risk: low
output_format: auto
output_folder: documents
task: document_generation
inputs:
  - name: title
    type: string
    required: true
    description: 문서 제목
  - name: source_text
    type: string
    required: true
    description: 회의 내용, 보고 사실, 업무 배경 등 원문/메모
  - name: audience
    type: string
    required: false
    description: 대상 독자
---
다음 입력을 바탕으로 회사 업무에 바로 사용할 수 있는 문서를 작성하세요.

제목: {{ title }}
대상 독자: {{ audience or "(미지정)" }}
원문/메모:
{{ source_text }}

작성 지침:
- 핵심 요약, 본문, 액션 아이템, 확인 필요사항을 포함하세요.
- 내용에 가장 적합한 출력 형식(markdown/html/csv/json/text)을 직접 선택하세요.
- 출력의 첫 줄에 선택한 형식을 `<!-- negotium:format=markdown -->` 형태로 명시한 뒤 본문을 작성하세요.
