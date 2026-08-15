# VMEC-05 G2 actual API contract

Verified from the current FastAPI route, Pydantic schema, runtime settings, and OpenAPI document on 2026-08-15.

`ANALYZE_ENDPOINT = POST /api/v1/analyze`

`ACTUAL_REQUEST_SCHEMA = AnalyzeRequest`

```json
{
  "patient_age": "integer, required, 0..120",
  "patient_gender": "required enum: male | female | other",
  "test_date": "required date, YYYY-MM-DD",
  "language": "string, optional, default vi",
  "indicators": [
    {
      "name": "non-empty string",
      "value": "finite number",
      "unit": "non-empty string"
    }
  ]
}
```

The HTTP field is `indicators`. `raw_indicators` is an internal graph-state field and is not accepted as the current HTTP request field.

`AUTH_REQUIRED = YES`

The route depends on `get_current_user`. Evaluation requests use a real guest bearer session from `POST /api/v1/auth/guest`; bearer tokens are never written to artifacts.

`REAL_LLM_PROVIDER = OpenAI-compatible/ChatOpenAI`

`REAL_LLM_MODEL = gpt-4o-mini`

`OPENAI_API_KEY_AVAILABLE = YES` was verified as a boolean only. No credential value was printed or stored.

`RAG_ENABLED = true`

`RAG_COLLECTION = medical_kb_v1`
