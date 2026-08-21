"""Che dữ liệu — kiểm trên ĐƯỜNG TRUYỀN, không phải kiểm hàm `_mask()`.

`test_langfuse_tracing.py` kiểm `_mask()` trả về đúng. Điều nó không kiểm được
là câu hỏi thật sự quan trọng: **SDK có thực sự gọi hàm đó trước khi gửi hay
không.** Một thay đổi trong Langfuse SDK, một tham số truyền sai, một đường đi
mà `mask` không được áp — cả ba đều làm unit test vẫn xanh trong khi giá trị xét
nghiệm của bệnh nhân đi thẳng ra máy chủ bên thứ ba.

Nên bộ test này dựng một máy chủ HTTP thật, trỏ `LANGFUSE_HOST` vào đó, chạy một
lời gọi LLM với đúng hình dạng prompt của analyzer, rồi quét toàn bộ byte đã gửi.

Cặp test này phải đi cùng nhau. Một mình test "bật che" là vô nghĩa: nó cũng xanh
khi callback không gửi gì cả. Test "tắt che" là đối chứng — nó chứng minh dữ liệu
THẬT SỰ có trên đường truyền, và chính việc che mới là thứ chặn lại.

## Vì sao phải chạy trong tiến trình con

Langfuse gắn hàm `mask` vào trạng thái OpenTelemetry TOÀN CỤC ngay lần dựng
client đầu tiên. `reset_for_tests()` xoá được client mà module này nhớ, nhưng
không xoá được tracer provider của SDK — nên lời gọi thứ hai trong cùng tiến
trình vẫn dùng cấu hình che của lần đầu. Chạy chung tiến trình thì test đối chứng
đỏ vì lý do không liên quan gì tới điều đang kiểm.

Điều đó cũng có hệ quả thật ở production, đáng ghi lại: **cấu hình che bị chốt
bởi client đầu tiên được dựng trong tiến trình.** Không đổi được lúc đang chạy,
và nếu có đoạn code nào dựng client trước khi settings hoàn chỉnh thì che có thể
sai. Hiện tại `get_client()` chỉ dựng lười khi có lời gọi LLM đầu tiên nên không
sao, nhưng ai chuyển nó sang khởi tạo lúc import cần biết chuyện này.
"""

from __future__ import annotations

import gzip
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Đúng hình dạng prompt mà analyzer_node dựng: tuổi, giới, tên chỉ số, giá trị,
# đơn vị, khoảng tham chiếu.
PROMPT = (
    "Bệnh nhân nữ 54 tuổi. Chỉ số Đường huyết lúc đói là 9.8 mmol/L, "
    "khoảng tham chiếu 3.9-5.6 mmol/L. Hãy giải thích cho bệnh nhân."
)
ANSWER = "Kết quả Đường huyết lúc đói 9.8 mmol/L của bạn cao hơn khoảng tham chiếu."

# Những chuỗi tuyệt đối không được rời khỏi tiến trình khi bật che.
#
# Toàn CỤM TỪ, không con số trần. Bản đầu quét `"54"` và `"9.8"`, rồi đỏ chập
# chờn vì hai ký tự `54` trúng ngẫu nhiên vào span id hoặc số cổng — chạy lại
# thì xanh. Một assertion bảo mật chập chờn còn tệ hơn không có: nó dạy người
# đọc bỏ qua màu đỏ. Cụm tiếng Việt có dấu thì không thể trùng ngẫu nhiên với
# protobuf hay id hex.
PATIENT_DATA = [
    "9.8 mmol/L",
    "54 tuổi",
    "Đường huyết lúc đói",
    "3.9-5.6",
    "cao hơn khoảng tham chiếu",
]


class _Capture(BaseHTTPRequestHandler):
    """Nhận mọi POST, giải nén nếu cần, cất nguyên byte lại để soi."""

    captured: list[bytes] = []

    def do_POST(self) -> None:  # noqa: N802 - chữ ký của BaseHTTPRequestHandler
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        if self.headers.get("Content-Encoding") == "gzip":
            try:
                body = gzip.decompress(body)
            except Exception:
                pass
        type(self).captured.append(body)
        self.send_response(207)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"successes":[],"errors":[]}')

    def log_message(self, *args) -> None:  # noqa: D102 - im lặng, đừng bẩn output test
        pass


def _bytes_sent_by_one_llm_call(*, masked: bool) -> str:
    """Chạy một lời gọi LLM ở tiến trình con, trả về byte nó đã gửi dạng text.

    Máy chủ bắt gói nằm ở tiến trình CHA để soi trực tiếp; chỉ phần gửi mới chạy
    ở tiến trình con, vì đó mới là chỗ dính trạng thái OTel toàn cục.

    Cổng 0 để hệ điều hành tự chọn: cố định cổng thì hai test chạy song song,
    hoặc một tiến trình cũ chưa chết, sẽ làm đỏ theo kiểu không liên quan gì tới
    nội dung đang kiểm.
    """

    handler_class = type("Capture", (_Capture,), {"captured": []})
    server = HTTPServer(("127.0.0.1", 0), handler_class)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(port), "true" if masked else "false"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"tiến trình con hỏng:\n{result.stdout}\n{result.stderr}"

        deadline = time.monotonic() + 10
        while not handler_class.captured and time.monotonic() < deadline:
            time.sleep(0.1)
    finally:
        server.shutdown()
        server.server_close()

    assert handler_class.captured, "không gói nào rời tiến trình — callback có thể không chạy"
    return b"".join(handler_class.captured).decode("utf-8", errors="replace")


def test_no_patient_data_leaves_the_process_when_masking_is_on():
    """Bảo đảm cốt lõi của phương án "che, chỉ gửi metadata"."""

    wire = _bytes_sent_by_one_llm_call(masked=True)

    leaked = [needle for needle in PATIENT_DATA if needle in wire]

    assert not leaked, f"dữ liệu bệnh nhân rời khỏi tiến trình: {leaked}"


def test_the_same_call_does_leak_when_masking_is_off():
    """Đối chứng — không có test này thì test trên vô nghĩa.

    Nếu callback lặng lẽ ngừng gửi gì (đổi API, cấu hình sai, span rỗng) thì
    test "bật che" vẫn xanh trong khi thực tế là không có trace nào. Test này
    chứng minh dữ liệu THẬT SỰ đi qua đường đó, và chính việc che mới chặn lại.
    """

    wire = _bytes_sent_by_one_llm_call(masked=False)

    leaked = [needle for needle in PATIENT_DATA if needle in wire]

    assert leaked, (
        "tắt che mà vẫn không thấy dữ liệu nào trên đường truyền — "
        "nhiều khả năng callback không còn gửi gì, và test che ở trên đang xanh giả"
    )


# ---------------------------------------------------------------------------
# Tiến trình con: gửi đúng một lời gọi LLM rồi thoát.
#
# pytest không chạy khối này (nó chỉ thu các hàm `test_*`), nên để cùng file với
# test là gọn nhất — child và assertion dùng chung PROMPT/ANSWER, không thể lệch.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os

    port_arg, masked_arg = sys.argv[1], sys.argv[2]

    os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-lf-wire-test"
    os.environ["LANGFUSE_SECRET_KEY"] = "sk-lf-wire-test"
    os.environ["LANGFUSE_HOST"] = f"http://127.0.0.1:{port_arg}"
    os.environ["LANGFUSE_MASK_PAYLOADS"] = masked_arg

    sys.path.insert(0, str(REPO_ROOT))

    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from src.services import langfuse_tracing

    callback = langfuse_tracing.get_callback_handler()
    if callback is None:
        raise SystemExit("không dựng được callback Langfuse")

    FakeListChatModel(responses=[ANSWER], callbacks=[callback]).invoke(PROMPT)
    langfuse_tracing.flush()
