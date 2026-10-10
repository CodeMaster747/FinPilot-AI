// In-browser OCR with tesseract.js. The worker, WASM core and English model are bundled under /ocr,
// so nothing is downloaded from the internet and the image never leaves the device for OCR.
import type Tesseract from "tesseract.js";

import { api } from "@/lib/api";

export type OcrLine = { text: string; confidence: number; bbox: { x0: number; y0: number; x1: number; y1: number } };
export type OcrResult = { lines: OcrLine[]; text: string; width: number; height: number; confidence: number; image: string; ms: number };
export type OcrProgress = { status: string; progress: number };

const STATUS: Record<string, string> = {
  "loading tesseract core": "Loading the OCR engine",
  "initializing tesseract": "Starting the OCR engine",
  "loading language traineddata": "Loading the English model",
  "initializing api": "Starting the OCR engine",
  "recognizing text": "Reading the text",
};

let workerPromise: Promise<Tesseract.Worker> | null = null;
let listener: ((p: OcrProgress) => void) | null = null;

function getWorker(): Promise<Tesseract.Worker> {
  if (!workerPromise) {
    workerPromise = import("tesseract.js").then(async ({ createWorker, OEM }) => {
      const worker = await createWorker("eng", OEM.LSTM_ONLY, {
        workerPath: "/ocr/worker.min.js",
        corePath: "/ocr/core",
        langPath: "/ocr/lang",
        logger: (m) => listener?.({ status: STATUS[m.status] ?? m.status, progress: m.progress }),
      });
      // Photos carry no DPI; telling Tesseract one avoids its "Estimating resolution" console noise.
      await worker.setParameters({ user_defined_dpi: "300" });
      return worker;
    }).catch((e) => {
      workerPromise = null;
      throw e;
    });
  }
  return workerPromise;
}

/** Scale big phone photos down (OCR is slow on 12 MP images and gains nothing above ~2000 px). */
export async function prepareImage(file: Blob, maxSide = 2000): Promise<{ blob: Blob; url: string; width: number; height: number }> {
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.src = url;
  try {
    await img.decode();
  } catch {
    URL.revokeObjectURL(url);
    throw new Error("This image format can't be read in the browser. Use a JPG, PNG or WebP photo.");
  }
  const { naturalWidth: w, naturalHeight: h } = img;
  if (Math.max(w, h) <= maxSide) return { blob: file, url, width: w, height: h };
  const scale = maxSide / Math.max(w, h);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
  URL.revokeObjectURL(url);
  const blob = await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b!), "image/jpeg", 0.9));
  return { blob, url: URL.createObjectURL(blob), width: canvas.width, height: canvas.height };
}

export async function ocrImage(image: Blob, size: { width: number; height: number; url: string }, onProgress?: (p: OcrProgress) => void): Promise<OcrResult> {
  listener = onProgress ?? null;
  onProgress?.({ status: "Loading the OCR engine", progress: 0 });
  const t0 = performance.now();
  const worker = await getWorker();
  const { data } = await worker.recognize(image, { rotateAuto: true }, { text: true, blocks: true, imageColor: true });
  listener = null;
  const lines: OcrLine[] = (data.blocks ?? []).flatMap((b) => b.paragraphs.flatMap((p) => p.lines))
    .map((l) => ({ text: l.text.trim(), confidence: l.confidence, bbox: l.bbox }))
    .filter((l) => l.text);
  // When the photo was straightened, show the straightened image so the boxes line up with it.
  const rotated = Math.abs(data.rotateRadians ?? 0) > 0.005 && data.imageColor;
  const image64 = rotated ? (data.imageColor!.startsWith("data:") ? data.imageColor! : `data:image/png;base64,${data.imageColor}`) : size.url;
  return { lines, text: data.text, width: size.width, height: size.height, confidence: data.confidence, image: image64, ms: performance.now() - t0 };
}

export type ReceiptField = { value: string; confidence: number; bbox: OcrLine["bbox"] | null };
export type ReceiptFields = {
  merchant?: ReceiptField; date?: ReceiptField; total?: ReceiptField; gstin?: ReceiptField; cgst?: ReceiptField; sgst?: ReceiptField; igst?: ReceiptField;
  items?: { description: string; quantity: number; amount: string; confidence: number; bbox: OcrLine["bbox"] | null }[];
};

export function parseOcr(blob: Blob, filename: string, ocr: OcrResult, dryRun = false) {
  const fd = new FormData();
  fd.append("file", blob, filename);
  fd.append("ocr", JSON.stringify({ lines: ocr.lines, text: ocr.text, width: ocr.width, height: ocr.height }));
  if (dryRun) fd.append("dry_run", "true");
  return api<{ fields: ReceiptFields } & Record<string, unknown>>("/receipts/parse", { method: "POST", body: fd });
}
