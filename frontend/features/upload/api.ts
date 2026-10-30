import { apiClient } from "@/lib/api/client"
import axios from "axios"
import type { components } from "@/lib/api/schema"

export type DirectUploadTicketOut =
  components["schemas"]["DirectUploadTicketOut"]
export type UploadResponse = components["schemas"]["UploadResponse"]

export const uploadApi = {
  async createDirectUpload(
    filename: string,
    file_size_bytes: number
  ): Promise<DirectUploadTicketOut> {
    const res = await apiClient.post<DirectUploadTicketOut>(
      "/documents/direct-uploads",
      {
        filename,
        size: file_size_bytes,
      }
    )
    return res.data
  },

  async uploadToSignedUrl(
    uploadUrl: string,
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<void> {
    const formData = new FormData()
    formData.append("file", file)

    await axios.put(uploadUrl, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total) {
          const percent = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          )
          onProgress?.(percent)
        }
      },
    })
  },

  async completeDirectUpload(uploadId: string): Promise<any> {
    const res = await apiClient.post(
      `/documents/direct-uploads/${uploadId}/complete`
    )
    return res.data
  },

  async uploadMultipartFallback(
    files: File[],
    idempotencyKey?: string,
    onProgress?: (percent: number) => void
  ): Promise<UploadResponse> {
    const formData = new FormData()
    files.forEach((file) => formData.append("files", file))

    const res = await apiClient.post<UploadResponse>(
      "/documents/upload",
      formData,
      {
        headers: {
          "Content-Type": "multipart/form-data",
          ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
        },
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percent = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            )
            onProgress?.(percent)
          }
        },
      }
    )
    return res.data
  },
}
