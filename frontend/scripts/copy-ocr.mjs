// Копирует движок распознавания (Tesseract) и языковые модели в public/ocr,
// чтобы сайт и Android-приложение читали чеки без внешних сервисов и интернета.
import { copyFileSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const out = new URL("../public/ocr/", import.meta.url).pathname;
const pkgDir = (name) => dirname(require.resolve(`${name}/package.json`));

mkdirSync(join(out, "lang"), { recursive: true });
copyFileSync(join(pkgDir("tesseract.js"), "dist/worker.min.js"), join(out, "worker.min.js"));

// Только LSTM-варианты ядра (их выбирает tesseract.js при OEM.LSTM_ONLY), с wasm внутри js.
const core = pkgDir("tesseract.js-core");
for (const f of readdirSync(core)) {
  if (/^tesseract-core(-simd|-relaxedsimd)?-lstm\.wasm\.js$/.test(f)) copyFileSync(join(core, f), join(out, f));
}
for (const lang of ["rus", "eng"]) {
  const src = join(pkgDir(`@tesseract.js-data/${lang}`), "4.0.0_best_int", `${lang}.traineddata.gz`);
  copyFileSync(src, join(out, "lang", `${lang}.traineddata.gz`));
}
console.log("OCR assets ->", out);
