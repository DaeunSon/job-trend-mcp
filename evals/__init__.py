"""
MCP 도구 호출 평가 하네스.

같은 질문 세트를 모델별로 Claude API 에 보내고, 모델이 MCP 도구를 의도대로 썼는지
(도구 선택 · 파라미터 · 최종 숫자)와 응답시간 · 토큰 · 비용을 함께 기록한다.

실행: PYTHONPATH=. python scripts/run_eval.py --help
"""
