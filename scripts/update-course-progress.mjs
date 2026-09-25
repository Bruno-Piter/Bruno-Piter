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

const label = bar(percentage(saoPauloTodayUtc()));
const files = ["visual-dark.svg", "visual-light.svg"].map(
  (name) => new URL(`../assets/${name}`, import.meta.url),
);

for (const file of files) {
  let svg = readFileSync(file, "utf8");
  for (const name of COURSES) {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const pattern = new RegExp(
      `(\\{ name: "${escaped}", progress: ")[^"]+(" \\})`,
    );
    if (!pattern.test(svg)) {
      console.error(`Curso não encontrado (${name}) em ${file.pathname}`);
      process.exit(1);
    }
    svg = svg.replace(pattern, `$1${label}$2`);
  }
  writeFileSync(file, svg);
}

const readmePath = new URL("../README.md", import.meta.url);
const readme = readFileSync(readmePath, "utf8");
const views = await profileViewsBadge(readme);
if (views !== readme) writeFileSync(readmePath, views);

console.log(label);

async function profileViewsBadge(readme) {
  const pattern = /https:\/\/img\.shields\.io\/badge\/profile%20views-[^"'\s]+/;
  if (!pattern.test(readme)) return readme;
  try {
    const response = await fetch(
      "https://komarev.com/ghpvc/?username=Bruno-Piter&style=flat",
    );
    if (!response.ok) return readme;
    const match = (await response.text()).match(/PROFILE VIEWS:\s*([\d,]+)/);
    if (!match) return readme;
    const badge = `https://img.shields.io/badge/profile%20views-${encodeURIComponent(match[1])}-blueviolet?style=for-the-badge`;
    return readme.replace(pattern, badge);
  } catch {
    return readme;
  }
}
