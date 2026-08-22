import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_HOME, KNOWN_ROLES, homeForRole } from "./roleHome.mjs";

test("moi vai tro co trang chu rieng", () => {
  assert.equal(homeForRole("patient"), "/patient");
  assert.equal(homeForRole("doctor"), "/doctor");
  assert.equal(homeForRole("admin"), "/admin");
});

test("admin KHONG duoc roi vao trang benh nhan", () => {
  // Loi that: `role === "doctor" ? "/doctor" : "/patient"` day admin sang
  // /patient, trang do thay vai tro khong khop nen da tiep ve /login. Nguoi
  // dung thay "bam gi cung quay ve man dang nhap", mot trieu chung khong he
  // chi ve mot bieu thuc ba ngoi.
  assert.notEqual(homeForRole("admin"), "/patient");
  assert.notEqual(homeForRole("admin"), "/login");
});

test("khach ve man benh nhan vi khong co trang rieng", () => {
  assert.equal(homeForRole("guest"), "/patient");
});

test("vai tro la hoac thieu thi ve mac dinh, khong vo", () => {
  assert.equal(homeForRole(null), DEFAULT_HOME);
  assert.equal(homeForRole(undefined), DEFAULT_HOME);
  assert.equal(homeForRole(""), DEFAULT_HOME);
  assert.equal(homeForRole("vaitro_chua_ton_tai"), DEFAULT_HOME);
});

test("moi vai tro da biet deu tra ve mot duong dan that", () => {
  // Chot rang khong vai tro nao bi bo quen khi co nguoi them vai tro thu nam.
  for (const role of KNOWN_ROLES) {
    const home = homeForRole(role);
    assert.ok(home.startsWith("/"), `${role} -> ${home}`);
    assert.notEqual(home, "/login", `${role} khong duoc tro ve man dang nhap`);
  }
});
