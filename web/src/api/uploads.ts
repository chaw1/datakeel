import { post, requireSuccess } from "./client";

import type { components } from "./generated";

type UploadInput = components["schemas"]["UploadInput"];
type UploadView = components["schemas"]["UploadView"];

export interface FolderUpload {
  declaration: UploadInput;
  payload: Blob;
}

export async function uploadFolder(
  upload: FolderUpload,
  onProgress: (percent: number) => void,
) {
  const { declaration, payload } = upload;
  const receipt = await post<UploadView>("/api/uploads", declaration);
  const path = `/api/uploads/${encodeURIComponent(receipt.id)}`;
  const total = receipt.chunk_count;
  let done = receipt.received_chunks.length;
  onProgress(total ? Math.round((done / total) * 100) : 100);
  for (const ordinal of receipt.missing_chunks) {
    const begin = ordinal * receipt.chunk_bytes;
    const response = await fetch(`${path}/chunks/${String(ordinal)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/octet-stream" },
      body: payload.slice(begin, begin + receipt.chunk_bytes),
    });
    await requireSuccess(response);
    done += 1;
    onProgress(Math.round((done / total) * 100));
  }
  const complete = await post<UploadView>(`${path}/complete`, null);
  if (!complete.dataset_id) throw new Error();
  return complete.dataset_id;
}
