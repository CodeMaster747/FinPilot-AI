// Copies tesseract.js worker, WASM core and the English model into public/ocr so OCR runs fully
// offline in the browser (no CDN). Runs automatically before `next dev` and `next build`.
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const out = join(process.cwd(), "public", "ocr");
const pkgDir = (name) => dirname(require.resolve(`${name}/package.json`));

mkdirSync(join(out, "core"), { recursive: true });
mkdirSync(join(out, "lang"), { recursive: true });

cpSync(join(pkgDir("tesseract.js"), "dist", "worker.min.js"), join(out, "worker.min.js"));
for (const variant of ["lstm", "simd-lstm", "relaxedsimd-lstm"]) {
  const file = `tesseract-core-${variant}.wasm.js`;
  cpSync(join(pkgDir("tesseract.js-core"), file), join(out, "core", file));
}
const lang = join(pkgDir("@tesseract.js-data/eng"), "4.0.0_best_int", "eng.traineddata.gz");
if (!existsSync(lang)) throw new Error(`missing ${lang}`);
cpSync(lang, join(out, "lang", "eng.traineddata.gz"));
console.log("OCR assets copied to public/ocr");
