# AI Agent Giải Thích Kết Quả Xét Nghiệm Bằng Ngôn Ngữ Dễ Hiểu Cho Bệnh Nhân

> Bệnh nhân nhận phiếu kết quả xét nghiệm đầy chỉ số và thuật ngữ (WBC, HbA1c, LDL...) nhưng không hiểu ý nghĩa, lo lắng quá mức hoặc chủ quan, gọi hỏi bác sĩ/hotline nhiều. Cần AI Agent tiếp nhận phiếu kết quả (mô phỏng), đối chiếu khoảng tham chiếu, giải thích từng chỉ số bằng ngôn ngữ đơn giản, nêu chỉ số bất thường và ý nghĩa chung, gợi ý câu hỏi nên hỏi bác sĩ. Agent lập kế hoạch: phân tích - tra cứu chỉ số có nguồn - cá nhân hóa lời giải - tạo bản tóm tắt thân thiện.


## Link chạy thật (Live)

| Thành phần | URL | Ghi chú |
|---|---|---|
| Frontend | https://vmec-05.vercel.app | Next.js trên Vercel |
| Backend API | https://vmec-05-api-production.up.railway.app | FastAPI trên Railway |
| API docs | https://vmec-05-api-production.up.railway.app/docs | Swagger UI |
| Health / Readiness | `/health` · `/ready` | `/ready` báo cả trạng thái RAG |

Tài khoản demo: `benhnhan` / `benhnhan123` · `bacsi` / `bacsi123`

> Deploy chạy tay, **merge vào `main` không tự động cập nhật bản live**:
> `railway up --service vmec-05-api` (backend) và `vercel --prod` (frontend, chạy trong `frontend/`).

## Vấn đề (Problem)

Bệnh nhân ngoại trú 25-55 tuổi, vừa nhận phiếu sau khám sức khoẻ định kỳ hoặc theo dõi bệnh mãn tính, chưa có cuộc hẹn tái khám với bác sĩ, đang tự đọc phiếu một mình mà không có ai giải thích. Phiếu kết quả xét nghiệm đầy chỉ số và thuật ngữ (WBC, HbA1c, LDL...) nhưng không hiểu ý nghĩa, lo lắng quá mức hoặc chủ quan, gọi hỏi bác sĩ/hotline nhiều.

- Nhiều người lo lắng khi chỉ số xét nghiệm không giống bình thường (Nguồn: Tuoitre).
- Dẫn chứng bệnh nhân “mất ăn mất ngủ” vì một chỉ số tăng cao (Nguồn: Vietnamnet).
- Khoảng 67,3% người trưởng thành Việt Nam có năng lực đọc hiểu thông tin sức khỏe thấp (Nguồn: ScienceDirect).

Dẫn chứng dễ thấy nhất là người trẻ chúng ta, có bố mẹ bị mắc bệnh điển hình như tiểu đường, mỡ máu. Phụ huynh hàng tháng phải xét nghiệm định kỳ, ngồi tập trung tra dò từng chỉ số trên phiếu kết quả xét nghiệm phức tạp. Điều này gây tốn thời gian và trên hết ảnh hưởng đến tâm lý người bệnh khi kết quả “khác thường” đi một chút, dù thực tế là bình thường.


## Giải pháp (Solution)

Sản phẩm AI Agent giải thích kết quả xét nghiệm từng bước, thân thiện, dựa trên Web Search uy tín:

1. Input: Bệnh nhân dán/tải ảnh phiếu kết quả (OCR+classification → loại báo cáo & chỉ số); Agent nhận định đây là phiếu xét nghiệm.
2. Quy trình (thông qua LangGraph): Agent lập kế hoạch phân tích từng chỉ số → Web Search tìm kiếm khoảng tham chiếu + ý nghĩa y khoa với nguồn đáng tin (Mayo Clinic, MedlinePlus, bệnh viện uy tín) → phân tích so với khoảng tham chiếu → tạo lời giải thích đơn giản, nhấn mạnh chỉ số bất thường và ý nghĩa kèm rủi ro chung → trả lời câu hỏi tự nhiên của bệnh nhân → cuối cùng tóm tắt kết quả tổng quát.
3. Output: Trả về JSON: 
   - `summary`: giải thích ngắn bằng ngôn ngữ đời thường.
   - `abnormalities`: danh sách chỉ số bất thường và cảnh báo.
   - `suggestions`: gợi ý câu hỏi nên hỏi bác sĩ.
   - `sources`: nguồn tham khảo cho từng chỉ số.

## Target User

- Primary: Bệnh nhân ngoại trú 25-55 tuổi, vừa nhận phiếu sau khám sức khoẻ định kỳ hoặc theo dõi bệnh mãn tính, chưa có cuộc hẹn tái khám với bác sĩ, đang tự đọc phiếu một mình mà không có ai giải thích. 
- Secondary: Bác sĩ muốn giảm số cuộc gọi hỏi những câu cơ bản, nhưng vẫn cần kiểm soát được thông tin bệnh nhân nhận. 

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agent | LangGraph + [LLM] |
| Backend | FastAPI + Python 3.11+ |
| Frontend | React/Next.js + TypeScript |
| Database | PostgreSQL / SQLite |
| DevOps | Docker + GitHub Actions |

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/a20-ai-thuc-chien/A20-App-XXX.git
cd A20-App-XXX

# 2. Setup environment
cp .env.example .env
# Edit .env with your API keys

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run development server
uvicorn src.main:app --reload
```

## Project Structure

```
├── src/
│   ├── agents/          # LangGraph agent definitions
│   │   ├── graph.py     # Main graph (nodes + edges)
│   │   ├── state.py     # State schema
│   │   ├── nodes/       # Individual nodes
│   │   └── tools/       # Agent tools
│   ├── api/             # FastAPI routes
│   ├── models/          # Pydantic schemas
│   ├── services/        # Business logic
│   ├── config.py        # Settings
│   └── main.py          # App entry point
├── tests/               # Test suite
├── docs/                # Documentation
├── eval/                # Evaluation results
├── presentation/        # Demo materials
├── Dockerfile           # Multi-stage build
├── docker-compose.yml   # Full stack
└── .github/workflows/   # CI/CD pipelines
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /api/v1/chat | Chat with agent |
| POST | /api/v1/analyze | Analyze input |

## Deliverables Checklist

- [x] Source Code (GitHub)
- [x] README.md
- [x] Architecture Diagram (`docs/architecture_diagram.md`)
- [x] AI Logs (auto-collected)
- [x] Live URL / Deploy (xem mục [Link chạy thật](#link-chạy-thật-live))
- [ ] Video Demo
- [ ] Pitch Deck (`presentation/`)
- [x] Weekly Journal (`JOURNAL.md`)
- [x] Worklog (`WORKLOG.md`)
- [ ] Evaluation Evidence (`eval/results/`)

## Team

| Member | Role | Student ID |
|--------|------|-----------|
| NGUYỄN TUẤN DƯƠNG | Team Lead + PO + PM | 2A202601966 |
| TRẦN CHÍ VŨ | Tech Lead | 2A202601044 |
| TẠ QUỐC TUẤN | Developer | 2A202601114 |
| NGUYỄN HOÀNG DUY | Developer | 2A202601466 |

## License

MIT
