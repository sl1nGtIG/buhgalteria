// Чтение чеков прямо на устройстве: Tesseract для фото и скриншотов, PDF.js для PDF-квитанций.
// Без внешних сервисов и ключей: движок и языковые модели лежат в /ocr внутри сайта и приложения.
import type { Worker } from "tesseract.js";
import { isNative } from "./api";

type Progress = (message: string) => void;

const base = () => new URL("ocr/", document.baseURI).toString();

let workerPromise: Promise<Worker> | null = null;
let progressHandler: Progress = () => {};

function getWorker(): Promise<Worker> {
  if (!workerPromise) {
    workerPromise = (async () => {
      const { createWorker, OEM } = await import("tesseract.js");
      return createWorker(["rus", "eng"], OEM.LSTM_ONLY, {
        workerPath: `${base()}worker.min.js`,
        // Воркер грузится напрямую с того же адреса — так надёжнее в WebView Android-приложения.
        workerBlobURL: false,
        corePath: base(),
        langPath: `${base()}lang`,
        // При сборке APK Android распаковывает *.gz и убирает расширение — там модели без gzip.
        gzip: !isNative,
        logger: (m) => {
          if (m.status === "recognizing text") progressHandler(`Читаю чек… ${Math.round(m.progress * 100)}%`);
          else if (m.status.startsWith("loading")) progressHandler("Готовлю распознавание…");
        },
      });
    })();
    workerPromise.catch(() => (workerPromise = null));
  }
  return workerPromise;
}

/** Мелкий текст на скриншотах читается лучше, если картинку увеличить и сделать контрастной. */
async function prepare(image: Blob): Promise<HTMLCanvasElement | Blob> {
  try {
    const bitmap = await createImageBitmap(image);
    const scale = bitmap.width < 1400 ? Math.min(2, 1400 / bitmap.width) : 1;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d")!;
    ctx.filter = "grayscale(1) contrast(1.3)";
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return canvas;
  } catch {
    return image;
  }
}

export async function readImage(image: Blob, onProgress: Progress = () => {}): Promise<string> {
  progressHandler = onProgress;
  const worker = await getWorker();
  const { data } = await worker.recognize(await prepare(image));
  return data.text;
}

/** PDF банков обычно содержит текст; если это скан — распознаём страницы как картинки. */
export async function readPdf(file: Blob, onProgress: Progress = () => {}): Promise<string> {
  onProgress("Открываю PDF…");
  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
  const pdf = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
  const pages = Math.min(pdf.numPages, 5);

  const texts: string[] = [];
  for (let i = 1; i <= pages; i++) {
    const content = await (await pdf.getPage(i)).getTextContent();
    // Собираем строки по координате Y, чтобы «Сумма» и «5 000 ₽» оказались рядом.
    const rows = new Map<number, { x: number; s: string }[]>();
    for (const item of content.items) {
      if (!("str" in item) || !item.str.trim()) continue;
      const y = Math.round(item.transform[5]);
      const row = rows.get(y) ?? [];
      row.push({ x: item.transform[4], s: item.str });
      rows.set(y, row);
    }
    [...rows.entries()]
      .sort((a, b) => b[0] - a[0])
      .forEach(([, row]) => texts.push(row.sort((a, b) => a.x - b.x).map((r) => r.s).join(" ")));
  }
  const text = texts.join("\n").trim();
  if (text.length > 20) return text;

  // Скан без текстового слоя.
  const scanned: string[] = [];
  for (let i = 1; i <= pages; i++) {
    const page = await pdf.getPage(i);
    const viewport = page.getViewport({ scale: 2 });
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    await page.render({ canvas, viewport }).promise;
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/png"));
    if (blob) scanned.push(await readImage(blob, onProgress));
  }
  return scanned.join("\n");
}

export function readReceipt(file: Blob, onProgress?: Progress): Promise<string> {
  return file.type === "application/pdf" ? readPdf(file, onProgress) : readImage(file, onProgress);
}
