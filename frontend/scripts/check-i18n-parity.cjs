const fs = require("fs");
const path = require("path");

const modules = [
  "home",
  "classDetail",
  "smartGen",
  "learningAnalytics",
  "studentOps",
  "account",
  "prepPlan",
  "wuyu",
];
const dir = path.join(process.cwd(), "src/i18n/locales/modules");
let allOk = true;

for (const mod of modules) {
  const p = path.join(dir, mod + ".ts");
  if (!fs.existsSync(p)) {
    console.log(mod, "文件不存在");
    continue;
  }
  const src = fs.readFileSync(p, "utf8");
  const zhM = src.match(
    /export const \w*Zh[\s\S]*?= \{([\s\S]*?)\n\}[\s\S]*?(?:export const|$)/,
  );
  const enM = src.match(/export const \w*En[\s\S]*?= \{([\s\S]*?)\n\}/);
  if (!zhM || !enM) {
    console.log(mod, "解析失败 zhM=" + !!zhM + " enM=" + !!enM);
    allOk = false;
    continue;
  }
  const keysOf = (body) =>
    [...body.matchAll(/"([^"]+)"\s*:/g)].map((m) => m[1]);
  const zh = new Set(keysOf(zhM[1]));
  const en = new Set(keysOf(enM[1]));
  const onlyZh = [...zh].filter((k) => !en.has(k));
  const onlyEn = [...en].filter((k) => !zh.has(k));
  const enBody = enM[1];
  const cjkLines = enBody
    .split("\n")
    .filter((l) => /[一-鿿]/.test(l) && /:\s*['"]/.test(l))
    .map((l) => l.trim().slice(0, 70));
  const flag = onlyZh.length || onlyEn.length || cjkLines.length ? "⚠" : "✓";
  if (onlyZh.length || onlyEn.length || cjkLines.length) allOk = false;
  console.log(
    flag,
    mod,
    "Zh=" + zh.size,
    "En=" + en.size,
    "onlyZh=" + onlyZh.length,
    onlyZh.slice(0, 6).join(","),
    "onlyEn=" + onlyEn.length,
    onlyEn.slice(0, 6).join(","),
  );
  if (cjkLines.length) {
    console.log("    En含中文(前5):");
    cjkLines.slice(0, 5).forEach((l) => console.log("     " + l));
  }
}
console.log(allOk ? "ALL_OK" : "HAS_ISSUES");
