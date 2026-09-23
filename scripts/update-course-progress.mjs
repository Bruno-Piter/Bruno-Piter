import { readFileSync, writeFileSync } from "node:fs";

const START = Date.UTC(2026, 3, 30);
const END = Date.UTC(2028, 1, 10);
const COURSES = [
  "Software Engineering - USP/Esalq",
  "Google UX Design Professional",
];

function saoPauloTodayUtc() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = (type) => Number(parts.find((part) => part.type === type).value);
  return Date.UTC(value("year"), value("month") - 1, value("day"));
}

function percentage(today) {
  if (today <= START) return 0;
  if (today >= END) return 100;
  return Math.round(((today - START) / (END - START)) * 100);
}

function bar(percent) {
  const filled = Math.min(10, Math.max(0, Math.round(percent / 10)));
  return `${"█".repeat(filled)}${"·".repeat(10 - filled)} ${percent}%`;
}

const readmePath = new URL("../README.md", import.meta.url);
let readme = readFileSync(readmePath, "utf8");
const label = bar(percentage(saoPauloTodayUtc()));

for (const name of COURSES) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(
    `(\\{ name: "${escaped}", progress: ")[^"]+(" \\})`,
  );
  if (!pattern.test(readme)) {
    console.error(`Curso não encontrado no README: ${name}`);
    process.exit(1);
  }
  readme = readme.replace(pattern, `$1${label}$2`);
}

writeFileSync(readmePath, readme);
console.log(label);
