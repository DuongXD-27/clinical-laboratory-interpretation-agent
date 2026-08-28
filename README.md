# VMEC-05 — AI Agent Giải Thích Kết Quả Xét Nghiệm

Hệ thống AI Agent hỗ trợ giải thích kết quả xét nghiệm ngoại trú bằng ngôn ngữ dễ hiểu, có căn cứ y khoa và tuân thủ nghiêm ngặt các rào cản an toàn y tế (Medical Guardrails).

> **Tuyên bố miễn trừ trách nhiệm**: Đây là hệ thống thông tin giáo dục sức khỏe (Educational System), **KHÔNG** phải công cụ chẩn đoán y khoa, không thay thế ý kiến chuyên môn của bác sĩ hay nhân viên y tế có thẩm quyền.

---

## 1. Project Overview

- **Tiếp nhận kết quả xét nghiệm mô phỏng**: Nhập liệu qua giao diện biểu mẫu hoặc OCR phiếu xét nghiệm (Review Gate).
- **Reference Range Checker**: Đối chiếu chỉ số với khoảng tham chiếu chuẩn hóa theo độ tuổi/giới tính để phân loại trạng thái: `LOW` / `NORMAL` / `HIGH` / `UNKNOWN`.
- **Critical Detector**: Công cụ xác định giá trị nguy kịch độc lập và tất định (Deterministic), cảnh báo khẩn cấp khi vượt ngưỡng an toàn.
- **RAG Knowledge Retrieval**: Tra cứu tri thức y khoa đã được thẩm định từ tài liệu nguồn uy tín (Vinmec, Long Châu, Cleveland Clinic,...).
- **LLM Analyzer**: Diễn giải ý nghĩa chỉ số bằng ngôn ngữ phổ thông, gần gũi với người bệnh.
- **Medical Guardrail**: Chặn triệt để mọi hành vi chẩn đoán bệnh, suy đoán nguyên nhân cá nhân hóa hoặc chỉ định điều trị.
- **Doctor Questions Generator**: Gợi ý các câu hỏi trọng tâm để bệnh nhân chủ động trao đổi với bác sĩ trong lần khám tiếp theo.
- **Patient/Guest Conversational Assistant**: Trợ lý nổi trong giao diện bệnh nhân/khách để điều hướng kết quả, lịch sử, xu hướng, câu hỏi cho bác sĩ và luồng OCR đã review. Trợ lý không tự quyết định trạng thái y khoa; Agent V2 là nhánh rollout opt-in với canonical fallback.

### Canonical orchestrator scope

- **Roles hỗ trợ trên Assistant**: `guest`, `patient`.
- **Doctor conversational support**: deferred to V2; doctor-facing routes hiện có vẫn hoạt động riêng.
- **Six intents**: `UNSUPPORTED_OR_UNSAFE`, `ANALYZE_REPORT`, `EXPLAIN_CURRENT_RESULT`, `VIEW_HISTORY`, `ANALYZE_TREND`, `GET_DOCTOR_QUESTIONS`.
- **Seven SuggestedActions**: `OPEN_REPORT`, `VIEW_ABNORMAL`, `VIEW_HISTORY`, `VIEW_TREND`, `VIEW_DOCTOR_QUESTIONS`, `CONFIRM_OCR`, `RETRY`.
- **Onboarding bắt buộc**: Assistant chặn trước router/workflow cho tới khi người dùng xác nhận phạm vi sử dụng.
- **OCR HITL**: dữ liệu OCR chỉ đi vào phân tích qua `/api/v1/ocr/confirm`; Assistant chỉ đọc trạng thái pending và không sao chép OCR draft thành input y khoa.
- **History/Trend authorization**: patient chỉ truy cập dữ liệu của chính mình; guest bị chặn với `UNSUPPORTED_CAPABILITY`.
- **Tài liệu verify cuối**: [Orchestrator V1 Final Verify Evidence](docs/orchestrator-v1-final-verify.md).

---

## 2. Link chạy thật (Live)

| Thành phần | URL | Ghi chú |
|---|---|---|
| Frontend | https://vmec-05.vercel.app | Next.js trên Vercel |
| Backend API | https://vmec-05-api-production.up.railway.app | FastAPI trên Railway |
| API docs | https://vmec-05-api-production.up.railway.app/docs | Swagger UI |
| Health / Readiness | `/health` · `/ready` | `/ready` báo cả trạng thái RAG |

---

## 3. MVP Architecture

> Xem tài liệu đặc tả kiến trúc toàn diện và sơ đồ chi tiết tại [ARCHITECTURE.md](ARCHITECTURE.md).

### Luồng xử lý Pipeline

```text
Phiếu xét nghiệm (Manual / Reviewed OCR)
       │
       ▼
 FastAPI Backend (/api/v1/analyze)
       │
       ▼
 [1] Reference Range Checker ──► status: LOW | NORMAL | HIGH | UNKNOWN
       │
       ▼
 [2] Critical Detector ────────► is_critical: true/false
       │                         critical_status: critical_low | critical_high | null
       ▼
 [3] RAG Knowledge Retriever ──► Live Chunks từ ChromaDB (hoặc Curated Fallback)
       │
       ▼
[4] LLM Analyzer Node ────────► Diễn giải ngôn ngữ tự nhiên theo ngữ cảnh
       │
       ▼
[5] Medical Guardrail Node ───► Kiểm duyệt an toàn (Chặn chẩn đoán / đơn thuốc)
       │
       ▼
API JSON Response ────────────► Frontend Next.js (Dashboard / Báo cáo chi tiết)
```

### Luồng Patient/Guest Assistant

```text
Patient/Guest UI
       │
       ▼
Orchestrator API (/api/v1/orchestrator/message)
       │
       ▼
Role / Onboarding / OCR / Policy Gates
       │
       ▼
Intent Router -> Medical Context (`medical_context.py`) -> Workflow Dispatcher
       │
       ▼
Approved wrappers/services
       │
       ▼
Response Composer -> Medical Safety Validation -> Schema Validation
       │
       ▼
SuggestedAction Validation -> Frontend Assistant
```

Trong luồng này LLM chỉ được sinh `message`. Các trường `intent`, `status`, `reason_code`, `data`, `data_type`, `sources`, `suggested_actions` và `safety_notice` do server kiểm soát.

### Nguyên tắc phân tách trạng thái cốt lõi
- **Reference status**: `low` | `normal` | `high` | `unknown`
- **Critical state**: `is_critical` (boolean), `critical_status` (`critical_low` | `critical_high` | `null`)
- **Nguyên tắc phân định**: **Abnormal $\ne$ Critical** (Chỉ số bất thường vượt khoảng tham chiếu chưa chắc là giá trị nguy kịch; giá trị nguy kịch được kiểm tra qua ngưỡng riêng biệt).

---

## 4. Tech Stack

- **Backend**: FastAPI 0.115+, Python 3.11+, Uvicorn, Pydantic v2, Pydantic-Settings
- **Agent Orchestration**: LangGraph 0.2+, LangChain 0.3+
- **LLM Provider**: OpenAI (`gpt-4o-mini`) / Gemini (`langchain-google-genai`)
- **Embedding Provider**: OpenAI `text-embedding-3-small` (1536 dimensions)
- **Vector Database**: ChromaDB 0.5+ (`./data/chroma`)
- **OCR / Vision**: Gemini Vision (`gemini-3.5-flash-lite`), OpenRouter Vision Fallback (`google/gemma-4-26b-a4b-it:free`)
- **Database & Persistence**: SQLite (mặc định dev/demo tại `./data/app.db`), hỗ trợ PostgreSQL qua SQLAlchemy 2.0
- **Frontend**: Next.js 16 (App Router), React 19, TailwindCSS 4, TypeScript 5, Recharts

---

## 5. Prerequisites

- **Python**: Phiên bản 3.11 trở lên
- **Node.js**: Phiên bản 20.x trở lên
- **npm**: Đi kèm Node.js
- **Git**: Quản lý mã nguồn

---

## 6. Backend Setup

### Bước 1: Khởi tạo Virtual Environment và Cài đặt

**Trên Windows (PowerShell):**
```powershell
# Tạo virtual environment
python -m venv .venv

# Kích hoạt venv
.\.venv\Scripts\Activate.ps1

# Cài đặt runtime + lint/test tooling
pip install -r requirements-dev.txt
```

**Trên Linux / macOS (Bash):**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Dependency ownership is explicit: `requirements.txt` is the production/Docker
runtime authority, `requirements-dev.txt` adds lint and test tools, and
`requirements-eval.txt` adds optional evaluation tooling.

### Bước 2: Cấu hình biến môi trường
```powershell
# Copy cấu hình mẫu
cp .env.example .env
```
Mở file `.env` và điền API key cần thiết (xem chi tiết tại mục [Environment Variables](#7-environment-variables)).

### Bước 3: Khởi chạy Backend API
```powershell
uvicorn src.main:app --reload --port 8000
```
API sẽ hoạt động tại: `http://localhost:8000` (Swagger UI: `http://localhost:8000/docs`).

---

## 7. Frontend Setup

### Bước 1: Cài đặt Dependencies
```powershell
cd frontend
npm install
```

### Bước 2: Khởi chạy Frontend Dev Server
```powershell
npm run dev
```
Giao diện người dùng sẽ chạy tại: `http://localhost:3000`.

---

## 8. Environment Variables

Bảng cấu hình các biến môi trường trong file `.env`:

| Biến môi trường | Phân loại | Mục đích | Giá trị mặc định / Ví dụ |
|---|---|---|---|
| `OPENAI_API_KEY` | REQUIRED (nếu dùng OpenAI) | Khóa API gọi LLM và sinh Embedding | `sk-...` |
| `GOOGLE_API_KEY` | REQUIRED (nếu dùng Gemini/OCR) | Khóa API Gemini cho LLM và Vision OCR | `AIzaSy...` |
| `JWT_SECRET` | REQUIRED (Production) | Khóa ký phiên đăng nhập JWT | `dev-only-insecure-secret-change-me` |
| `APP_ENV` | DEFAULTED | Môi trường ứng dụng (`development`, `production`, `test`) | `development` |
| `APP_PORT` | DEFAULTED | Cổng mạng backend lắng nghe | `8000` |
| `APP_HOST` | DEFAULTED | Địa chỉ host backend bind | `0.0.0.0` |
| `CORS_ORIGINS` | DEFAULTED | Danh sách domain được phép gọi API (phân cách bằng dấu phẩy) | `http://localhost:3000,http://localhost:5173` |
| `DATABASE_URL` | DEFAULTED | Chuỗi kết nối CSDL SQLite hoặc PostgreSQL | `sqlite:///./data/app.db` |
| `RAG_ENABLED` | DEFAULTED | Bật/tắt tra cứu vector động qua ChromaDB | `false` |
| `RAG_COLLECTION_NAME` | DEFAULTED | Tên collection ChromaDB | `medical_kb_v4` |
| `RAG_CORPUS_VERSION` | DEFAULTED | Phiên bản dữ liệu tri thức y khoa | `medical-kb-v4` |
| `EMBEDDING_PROVIDER` | DEFAULTED | Nhà cung cấp embedding (`disabled`, `openai`, `gemini`) | `disabled` |
| `EMBEDDING_MODEL_NAME` | DEFAULTED | Tên model embedding | `text-embedding-3-small` |
| `CHROMA_PERSIST_DIR` | DEFAULTED | Đường dẫn lưu trữ vector DB | `./data/chroma` |
| `MODEL_NAME` | DEFAULTED | Tên mô hình LLM chính | `gpt-4o-mini` |
| `LLM_TIMEOUT_SECONDS` | DEFAULTED | Thời gian chờ tối đa cho 1 lượt gọi LLM | `20` |
| `GUEST_SESSION_EXPIRE_MINUTES` | DEFAULTED | Thời gian sống phiên khách | `120` |
| `OCR_REVIEW_TOKEN_EXPIRE_MINUTES` | DEFAULTED | Thời gian sống token review OCR | `15` |
| `OPENROUTER_API_KEY` | OPTIONAL | Khóa API OpenRouter dùng làm fallback OCR | `sk-or-v1-...` |
| `OCR_UPLOAD_MODE` | DEFAULTED | Chế độ nhận ảnh OCR (`demo_only`, `open_with_consent`, `internal_only`) | `demo_only` |
| `OCR_SAMPLES_DIR` | DEFAULTED | Thư mục chứa ảnh mẫu hợp lệ cho chế độ demo | `./data/ocr_samples` |
| `LANGCHAIN_API_KEY` | OPTIONAL | Khóa API LangSmith ghi nhận AI Trace | `lsv2_pt_...` |
| `AGENT_CHAT_V2` | DEFAULTED | Bật LangGraph Agentic RAG chat cho bệnh nhân (opt-in) | `false` |
| `NEXT_PUBLIC_API_URL` | FRONTEND | URL backend dùng trong `frontend/.env.local` | `http://localhost:8000` |

> [!IMPORTANT]
> **Cơ chế Rollout Agent V2**:
> - Khi `AGENT_CHAT_V2=false` (mặc định): Trợ lý sử dụng Canonical Orchestrator tất định.
> - Khi `AGENT_CHAT_V2=true`: Bệnh nhân đăng nhập sử dụng LangGraph Agent V2 runtime với khả năng gọi tool tự động; khách và các tình huống lỗi runtime tự động fallback an toàn về Canonical Orchestrator.
> - Để bật trên môi trường phát triển: thêm `AGENT_CHAT_V2=true` vào `.env` (hoặc PowerShell `$env:AGENT_CHAT_V2="true"`) và **khởi động lại backend**. Log khởi động sẽ hiển thị `"agent_chat_v2_enabled": true`.

> [!IMPORTANT]
> **Cơ chế RAG Fallback**:
> - Khi `RAG_ENABLED=false` (mặc định): Hệ thống kích hoạt cơ chế fallback sử dụng thư viện giải thích chuẩn hóa đã kiểm duyệt (Curated Reference Explanations), không phụ thuộc vào kết nối vector store ngoài.
> - Khi `RAG_ENABLED=true`: Cần cấu hình `EMBEDDING_PROVIDER=openai`, cung cấp `OPENAI_API_KEY` hợp lệ và đã chạy lệnh build vector store index vào ChromaDB.

---

## 9. Build / Rebuild RAG Knowledge Index

Dữ liệu tri thức giải thích y khoa nguồn nằm tại `data/reference/explanations.json`. Để lập chỉ mục vào ChromaDB:

```powershell
# Đảm bảo đã kích hoạt virtual environment và set RAG_ENABLED=true trong .env
python src/scripts/ingest_kb.py
```

Quy trình xử lý:
1. Đọc danh mục chỉ số và nội dung giải thích từ `data/reference/explanations.json`.
2. Tạo văn bản ngữ cảnh kèm nguồn trích dẫn.
3. Sinh vector embedding qua `OpenAIEmbeddings` (`text-embedding-3-small`, 1536 chiều).
4. Lưu trữ và lập chỉ mục vào thư mục ChromaDB cục bộ (`./data/chroma`).

*(Lưu ý: Thư mục `data/chroma` được gitignore theo quy chuẩn, môi trường mới cần chạy script ingest nếu muốn bật tính năng RAG động).*

---

## 10. Run the Application

| Dịch vụ | URL | Ghi chú |
|---|---|---|
| **Frontend Web** | `http://localhost:3000` | Giao diện Next.js cho người dùng |
| **Backend API** | `http://localhost:8000` | FastAPI service |
| **Swagger UI Docs** | `http://localhost:8000/docs` | Tài liệu API tương tác |
| **Readiness Check** | `http://localhost:8000/ready` | Báo cáo chi tiết trạng thái API và RAG |
| **Health Check** | `http://localhost:8000/health` | Kiểm tra kết nối cơ bản |

**Tài khoản đăng nhập có sẵn (Demo seed tự động):**
- **Bệnh nhân**: Tên đăng nhập `benhnhan` / Mật khẩu `benhnhan123`
- **Bác sĩ**: Tên đăng nhập `bacsi` / Mật khẩu `bacsi123`
- **Khách vãng lai**: Nhấn "Dùng thử ngay" trên giao diện để nhận token phiên khách (Guest session).

---

## 11. Sample Queries

Dưới đây là các truy vấn mẫu gửi đến endpoint `POST /api/v1/analyze`:

### Case A: Potassium 5.8 mmol/L (Abnormal nhưng Non-Critical)
- **Mục đích**: Kiểm chứng phân tách *Abnormal $\ne$ Critical*.
- **Payload**:
```json
{
  "patient_age": 35,
  "patient_gender": "male",
  "test_date": "2026-08-15",
  "language": "vi",
  "indicators": [
    {
      "name": "Potassium",
      "value": 5.8,
      "unit": "mmol/L"
    }
  ]
}
```
- **Kết quả kỳ vọng**: `status = "high"`, `is_critical = false`, `critical_status = null`, `critical_alerts = []`.

### Case B: Potassium 6.5 mmol/L (Critical High)
- **Mục đích**: Kiểm chứng luồng phát hiện giá trị nguy kịch cao.
- **Payload**:
```json
{
  "patient_age": 35,
  "patient_gender": "male",
  "test_date": "2026-08-15",
  "language": "vi",
  "indicators": [
    {
      "name": "Potassium",
      "value": 6.5,
      "unit": "mmol/L"
    }
  ]
}
```
- **Kết quả kỳ vọng**: `status = "critical_high"`, `is_critical = true`, có 1 cảnh báo nguy kịch nêu rõ ngưỡng $> 6.1\text{ mmol/L}$.

### Case C: Generic Glucose 5.2 mmol/L (Fail-Closed / An toàn)
- **Mục đích**: Kiểm chứng chỉ số không rõ danh mục ("Glucose" không tự map sang "Fasting plasma glucose").
- **Payload**:
```json
{
  "patient_age": 35,
  "patient_gender": "male",
  "test_date": "2026-08-15",
  "language": "vi",
  "indicators": [
    {
      "name": "Glucose",
      "value": 5.2,
      "unit": "mmol/L"
    }
  ]
}
```
- **Kết quả kỳ vọng**: `status = "unknown"`, `is_critical = false`, `reference_low = null`, `reference_high = null`, chuyển hướng tham vấn an toàn.

### Ví dụ gọi API qua PowerShell
```powershell
# 1. Lấy token phiên khách
$guest = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/guest" -Method Post
$token = $guest.access_token

# 2. Gửi request phân tích
$body = @{
    patient_age = 35
    patient_gender = "male"
    test_date = "2026-08-15"
    language = "vi"
    indicators = @(
        @{
            name = "Potassium"
            value = 5.8
            unit = "mmol/L"
        }
    )
} | ConvertTo-Json

$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
}

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/analyze" -Method Post -Headers $headers -Body $body
```

---

## 12. Tests

### Chạy kiểm thử tự động

**Full local verification (non-mutating):**
```powershell
make verify
```

This runs repository-wide Ruff lint and format checks, the backend suite with a
repository-local pytest temp base, the frontend lint/test/build scripts, and the
generated-artifact guard. It does not install dependencies, rewrite source, or
update lockfiles.

Equivalent direct commands (including Windows environments without GNU Make):
```powershell
ruff check .
ruff format --check .
python -m pytest -v --basetemp scratch/pytest-local
python scripts/check_tracked_generated_artifacts.py
cd frontend
npm run lint
npm test
npm run build
```

**Backend Unit & Integration Tests:**
```powershell
make test
```

**Kiểm tra Linting & Định dạng code:**
```powershell
make lint
```

`make format-check` is non-mutating and must pass. `make format` is the explicit
mutating formatter command. Python type checking is not part of verification
because no supported Python type checker is declared.

**Frontend Unit Tests:**
```powershell
cd frontend
npm test
```

**Frontend TypeScript Typecheck:**
```powershell
cd frontend
npx tsc --noEmit
```

**Frontend Production Build:**
```powershell
cd frontend
npm run build
```

**Focused Orchestrator / Safety Verify:**
```powershell
pytest tests/orchestrator -q
pytest tests/test_eval -q
pytest tests/test_data/test_medical_kb_manifest_integrity.py -q
```

### Trạng thái hồi quy Orchestrator V1

Kết quả cuối cùng được ghi trong [Orchestrator V1 Final Verify Evidence](docs/orchestrator-v1-final-verify.md) và Final Verify Report. Không dùng các số lịch sử cũ để thay thế kết quả test hiện tại.

---

## 13. Evaluation

Install optional evaluation dependencies with `pip install -r requirements-eval.txt`.
Evaluation datasets and retained run evidence live under
`eval/`; they are not installed into the production container.

Các báo cáo và bằng chứng kiểm nghiệm chi tiết của hệ thống:

- [Manual E2E Evaluation Evidence](eval/manual_e2e_evidence.md) — Kiểm chứng thực nghiệm 5 ca E2E chính + 1 ca an toàn bổ sung trên runtime thực tế.
- [G2 Final Evaluation Summary](eval/G2_EVALUATION_SUMMARY.md) — Tổng kết toàn diện các tiêu chí đánh giá G2.
- [API Contract Evidence](eval/api_contract.md) — Đặc tả và xác nhận schema API `/api/v1/analyze`.
- [Safety Evaluation Results](eval/safety/post_safety_fix_safety_eval.md) — Đánh giá an toàn y khoa độc lập 10 tiêu chí sau khắc phục.
- [OCR Accuracy Results](eval/ocr/ocr_accuracy_results.md) — Kết quả đo lường độ chính xác trích xuất OCR phiếu xét nghiệm.
- [Latency Benchmark](eval/performance/latency_summary.md) — Đo lường độ trễ chi tiết từng giai đoạn qua Server-Timing.
- [Live RAG Sanity Probes](eval/rag/live_rag_sanity.md) — Bằng chứng truy xuất vector trực tiếp từ ChromaDB.
- [RAGAS Benchmark Note](eval/results/G2_RAGAS_SCOPE_NOTE.md) — Bằng chứng lịch sử G2. TIP-007 không sinh live RAGAS quality score mới; trạng thái hiện tại là `RAG_LIVE_QUALITY=NOT MEASURED`.
- [Orchestrator V1 Final Verify Evidence](docs/orchestrator-v1-final-verify.md) — Traceability, P0/P1/P2, E2E, OCR/RAG/Auth boundaries và known limitations của Orchestrator V1.

---

## 14. Safety & Limitations

- **Không chẩn đoán**: Hệ thống không đưa ra bất kỳ kết luận chẩn đoán bệnh lý nào.
- **Không kê đơn / chỉ định điều trị**: Tuyệt đối không gợi ý dùng thuốc, liều lượng hoặc phương pháp chữa trị.
- **Không suy diễn nguyên nhân cá nhân**: Không quy chụp nguyên nhân bất thường cho một bệnh nhân cụ thể.
- **Ý nghĩa của NORMAL**: Giá trị "Bình thường" chỉ biểu thị số đo nằm trong khoảng tham chiếu mà hệ thống đang sử dụng đối chiếu.
- **Ý nghĩa của HIGH / LOW**: Tăng/giảm ngoài khoảng tham chiếu không tự động đồng nghĩa với tình trạng nguy kịch.
- **Tính tất định của Giá trị Nguy kịch (Critical Values)**: Được kiểm soát bởi Deterministic Rule Engine với ngưỡng cố định, hoàn toàn không phụ thuộc vào suy luận xác suất của LLM.
- **Unsupported analyte fail-closed**: `status="unknown"` không gọi general RAG và không gọi LLM giải thích; chỉ cho phép nội dung curated đã phê duyệt nếu có.
- **Conversation persistence có kiểm soát**: Patient conversations are persisted with ownership enforced by the server-side conversation repository; guest context remains short-lived and cannot access patient history.
- **Doctor Assistant deferred**: Bác sĩ dùng các route/app doctor hiện có; chatbot doctor không thuộc V1.
- **RAG live quality**: TIP-007 không đo live RAGAS quality score mới.
- **Phạm vi kiểm thử**: Các kết quả kiểm nghiệm hiện tại phản ánh tập dữ liệu xét nghiệm và các chỉ số được hỗ trợ trong phạm vi MVP, không đảm bảo tính đúng đắn cho mọi tình huống bệnh lý hay mọi định dạng phiếu xét nghiệm nằm ngoài danh mục.
