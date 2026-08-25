"""Ket noi chet khong duoc bien thanh 500 cho nguoi dung.

Bo test nay ra doi tu mot loi do duoc tren production, khong phai tu suy doan:

    POST /api/v1/auth/login  ->  500 sau 2.17ms
    psycopg2.OperationalError: SSL connection has been closed unexpectedly
    SELECT ... FROM users WHERE users.username = 'admin.duy'

Neon free tier ngu khi ranh va dong ket noi tu phia no. Pool cua SQLAlchemy
khong biet, van giao ket noi chet ra, va cau truy van dau tien sau moi khoang
lang no ngay. Nguoi dung thay "He thong dang ban" roi thu lai thi duoc — dung
kieu loi de bi cho qua vi khong tai hien duoc theo y muon.
"""

from __future__ import annotations

import src.models.db as db_module


def test_engine_checks_connection_health_before_handing_it_out():
    """`pool_pre_ping` la thu chan dung lop loi da xay ra that.

    Khong co no thi moi khoang lang cua Neon deu doi lay mot request 500 cho
    nguoi dung xui xeo dau tien quay lai.
    """

    assert db_module.engine.pool._pre_ping is True


def test_engine_recycles_connections_before_the_provider_drops_them():
    """Chu dong bo ket noi cu, thay vi doi Neon dong truoc.

    pre_ping da du de khong con 500, nhung moi lan ping mot ket noi da chet la
    mot vong mang lang phi. Recycle ngan hon thoi gian nhan roi cua Neon thi
    phan lon ket noi chet duoc thay truoc khi co ai cham vao.
    """

    recycle = db_module.engine.pool._recycle

    assert recycle > 0, "khong recycle thi ket noi cu nam mai trong pool"
    assert recycle <= 600, "recycle qua dai thi khong con tac dung phong ngua"
