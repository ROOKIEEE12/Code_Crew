import type { ImageUpload } from "./api";

export const MAX_IMAGES = 4;
const MAX_SIDE = 1600;

export interface PreparedImage {
  upload: ImageUpload;
  /** object URL for the thumbnail; revoke when removed */
  preview: string;
  name: string;
}

/** Scales an image down so its longest side is at most 1600px and re-encodes it
 *  as JPEG: small enough to upload quickly, large enough for a model to read. */
export async function prepareImage(file: File): Promise<PreparedImage> {
  if (!file.type.startsWith("image/")) throw new Error(`${file.name || "That file"} is not an image.`);
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const g = canvas.getContext("2d");
  if (!g) throw new Error("Your browser could not read that image.");
  g.fillStyle = "#fff"; // transparent PNGs get a white background instead of black
  g.fillRect(0, 0, canvas.width, canvas.height);
  g.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  if (!blob) throw new Error("Your browser could not read that image.");
  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(new Error("Could not read the image."));
    reader.readAsDataURL(blob);
  });
  return { upload: { media_type: "image/jpeg", data }, preview: URL.createObjectURL(blob), name: file.name || "pasted image" };
}

export function imagesFrom(list: FileList | DataTransferItemList | null | undefined): File[] {
  if (!list) return [];
  const out: File[] = [];
  for (const item of Array.from(list as ArrayLike<File | DataTransferItem>)) {
    const file = item instanceof File ? item : item.kind === "file" ? item.getAsFile() : null;
    if (file && file.type.startsWith("image/")) out.push(file);
  }
  return out;
}
