import type { FolderUpload } from "../../api/uploads";

interface FolderSource {
  path: string;
  file: File;
}

export interface FolderImage extends FolderSource {
  caption?: string;
  annotation?: string;
  readable: boolean;
}

export interface FolderSelection {
  name: string;
  images: FolderImage[];
  sources: Map<string, FolderSource>;
  ignored: number;
}

interface FolderSources {
  name: string;
  sources: Map<string, FolderSource>;
  total: number;
}

const imageExtension = /\.(png|jpe?g|webp)$/i;
const sidecarExtension = /\.(txt|json)$/i;
const splitNames = new Set(["train", "val", "test"]);
const textEncoder = new TextEncoder();
const chunkBytes = 1024 * 1024;
const maxBytes = 256 * chunkBytes;
const maxFiles = 2000;

function pathFor(file: File) {
  const parts = file.webkitRelativePath
    ? file.webkitRelativePath.split("/").slice(1)
    : [file.name];
  if (parts.some((part) => part.startsWith("."))) return undefined;
  if (!splitNames.has(parts[0] ?? "")) parts.unshift("train");
  const path = parts.join("/");
  if (!imageExtension.test(path) && !sidecarExtension.test(path))
    return undefined;
  if (
    parts.some(
      (part) =>
        !part || /[\\\0]/.test(part) || textEncoder.encode(part).length > 255,
    ) ||
    textEncoder.encode(path).length > 1024
  )
    throw new Error("importPathError");
  return path;
}

function folderSources(files: File[]): FolderSources {
  const sources = new Map<string, FolderSource>();
  for (const file of files) {
    const path = pathFor(file);
    if (!path) continue;
    if (sources.has(path)) throw new Error("importPathError");
    sources.set(path, { path, file });
  }
  const name = files[0]?.webkitRelativePath.split("/")[0] || "";
  return { name, sources, total: files.length };
}

async function canRead(file: File) {
  try {
    const image = await createImageBitmap(file, {
      resizeWidth: 96,
      resizeHeight: 96,
      resizeQuality: "low",
    });
    image.close();
    return true;
  } catch {
    return false;
  }
}

function pairedNames(path: string, sources: Map<string, FolderSource>) {
  const stem = path.slice(0, path.lastIndexOf("."));
  const prefix = path.slice(0, path.lastIndexOf("/") + 1);
  const caption = [
    `${stem}.txt`,
    `${prefix}caption.txt`,
    `${prefix}caption.json`,
    `${stem}.json`,
  ].find((candidate) => sources.has(candidate));
  const annotation = [
    `${stem}.annotations.json`,
    `${prefix}annotations.json`,
    `${stem}.json`,
  ].find((candidate) => sources.has(candidate));
  return { caption, annotation };
}

function usedSources(
  images: FolderImage[],
  sources: Map<string, FolderSource>,
) {
  const retained = new Set(
    images.flatMap(({ path, caption, annotation }) => [
      path,
      caption,
      annotation,
    ]),
  );
  return [...sources.values()].filter(({ path }) => retained.has(path));
}

export async function previewFolder(files: File[]): Promise<FolderSelection> {
  const { name, sources, total } = folderSources(files);
  const pictures = [...sources.values()].filter(({ path }) =>
    imageExtension.test(path),
  );
  if (!pictures.length) throw new Error("importNoImages");
  if (pictures.length > maxFiles) throw new Error("importSizeLimit");
  const images: FolderImage[] = [];
  for (const item of pictures) {
    images.push({
      ...item,
      ...pairedNames(item.path, sources),
      readable: await canRead(item.file),
    });
  }
  return {
    name,
    images,
    sources,
    ignored: total - usedSources(images, sources).length,
  };
}

export async function prepareFolderUpload(
  selection: FolderSelection,
  images: FolderImage[],
  name: string,
): Promise<FolderUpload> {
  const files = usedSources(images, selection.sources);
  const size = files.reduce((sum, { file }) => sum + file.size, 0);
  if (size > maxBytes || files.length > maxFiles)
    throw new Error("importSizeLimit");
  const payload = new Blob(files.map(({ file }) => file));
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await payload.arrayBuffer(),
  );
  const sha256 = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return {
    payload,
    declaration: {
      idempotency_key: crypto.randomUUID(),
      name,
      filename: "image-folder.bin",
      chunk_bytes: chunkBytes,
      total_bytes: size,
      sha256,
      folder: files.map(({ path, file }) => ({ path, size: file.size })),
    },
  };
}
