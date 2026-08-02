import json
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.agents.graph import build_graph

async def main():
    agent = build_graph()
    
    with open("data/mock/generated/normal.json", "r", encoding="utf-8") as f:
        request_data = json.load(f)
        
    # If the JSON is a list of reports, pick the first one
    if isinstance(request_data, list):
        report = request_data[0]
    else:
        report = request_data

    indicators = report.get("indicators", [])

    initial_state = {
        "patient_age": report.get("patient_age", 30),
        "patient_gender": report.get("patient_gender", "male"),
        "test_date": report.get("test_date", "2026-08-01"),
        "language": "vi",
        "raw_indicators": indicators
    }
    
    print("Invoking graph...")
    final_state = await agent.ainvoke(initial_state)
    
    print("\n--- Final State Indicators (with LLM Explanations) ---")
    for ind in final_state.get("indicators", []):
        print(f"\nChỉ số: {ind.get('name')}")
        print(f"Giá trị: {ind.get('value')} {ind.get('unit')}")
        print(f"Trạng thái: {ind.get('status')}")
        print(f"Giải thích: {ind.get('explanation')}")
        print(f"Nguồn: {ind.get('sources')}")
        
    print("\n--- Guardrail & Critical ---")
    print(f"Has critical values: {final_state.get('has_critical_values')}")
    print(f"Critical alerts: {final_state.get('critical_alerts')}")
    print(f"Guardrail passed: {final_state.get('guardrail_passed')}")
    
if __name__ == "__main__":
    asyncio.run(main())
