import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  CANONICAL_PATIENT_NAV_ITEMS,
  CANONICAL_PATIENT_SUBROUTES,
  PATIENT_ROUTES,
  getPatientPageTitle,
  isNavActive,
} from "./patientRoutes.mjs";

const APP_DIR = path.resolve(import.meta.dirname, "../app");

function resolveAppRouteFilePath(routePath) {
  const normalized = routePath.replace(/^\/+/, "");
  if (!normalized) {
    return path.join(APP_DIR, "page.tsx");
  }
  return path.join(APP_DIR, normalized, "page.tsx");
}

function routeExistsOnDisk(routePath) {
  const targetFile = resolveAppRouteFilePath(routePath);
  return fs.existsSync(targetFile);
}

test("every canonical patient sidebar navigation item points to a real App Router page", () => {
  assert.equal(CANONICAL_PATIENT_NAV_ITEMS.length, 5);

  for (const item of CANONICAL_PATIENT_NAV_ITEMS) {
    const pageFile = resolveAppRouteFilePath(item.href);
    const exists = fs.existsSync(pageFile);
    assert.ok(
      exists,
      `Route "${item.href}" (${item.label}) does not have an App Router page at: ${pageFile}`,
    );
  }
});

test("canonical patient route constants all map to real App Router pages", () => {
  const routesToVerify = [
    { name: "HOME", path: PATIENT_ROUTES.HOME },
    { name: "ANALYSIS", path: PATIENT_ROUTES.ANALYSIS },
    { name: "HISTORY", path: PATIENT_ROUTES.HISTORY },
    { name: "TRENDS", path: PATIENT_ROUTES.TRENDS },
    { name: "PROFILE", path: PATIENT_ROUTES.PROFILE },
    { name: "REPORT_DETAIL", path: PATIENT_ROUTES.REPORT_DETAIL_TEMPLATE },
    { name: "HISTORY_REPORT_DETAIL", path: PATIENT_ROUTES.HISTORY_REPORT_DETAIL_TEMPLATE },
  ];

  for (const route of routesToVerify) {
    assert.ok(
      routeExistsOnDisk(route.path),
      `PATIENT_ROUTES.${route.name} ("${route.path}") must point to a real page.tsx on disk`,
    );
  }
});

test("canonical patient subroutes all point to real App Router pages", () => {
  for (const item of CANONICAL_PATIENT_SUBROUTES) {
    assert.ok(
      routeExistsOnDisk(item.href),
      `Subroute "${item.href}" (${item.label}) must point to a real page.tsx on disk`,
    );
  }
});

test("isNavActive correctly identifies active routes and subroutes", () => {
  const homeItem = CANONICAL_PATIENT_NAV_ITEMS.find((i) => i.href === PATIENT_ROUTES.HOME);
  const analysisItem = CANONICAL_PATIENT_NAV_ITEMS.find((i) => i.href === PATIENT_ROUTES.ANALYSIS);
  const historyItem = CANONICAL_PATIENT_NAV_ITEMS.find((i) => i.href === PATIENT_ROUTES.HISTORY);

  assert.ok(isNavActive("/patient", homeItem));
  assert.equal(isNavActive("/patient/analysis", homeItem), false); // exact match on home

  assert.ok(isNavActive("/patient/analysis", analysisItem));
  assert.ok(isNavActive("/patient/analysis?mode=ocr", analysisItem));

  assert.ok(isNavActive("/patient/history", historyItem));
  assert.ok(isNavActive("/patient/reports/42", historyItem));
  assert.equal(isNavActive("/patient/trends", historyItem), false);
});

test("getPatientPageTitle derives accurate titles for all routes", () => {
  assert.equal(getPatientPageTitle("/patient"), "Tổng quan");
  assert.equal(getPatientPageTitle("/patient/analysis"), "Phân tích xét nghiệm");
  assert.equal(getPatientPageTitle("/patient/history"), "Lịch sử kết quả");
  assert.equal(getPatientPageTitle("/patient/trends"), "Xu hướng chỉ số");
  assert.equal(getPatientPageTitle("/patient/profile"), "Thông tin cá nhân");
  assert.equal(getPatientPageTitle("/patient/reports/123"), "Kết quả xét nghiệm");
});

test("route checker fails for nonexistent or misspelled routes", () => {
  assert.equal(routeExistsOnDisk("/patient/nonexistent"), false);
  assert.equal(routeExistsOnDisk("/patient/analyses"), false);
  assert.equal(routeExistsOnDisk("/patient/analytic"), false);
});
