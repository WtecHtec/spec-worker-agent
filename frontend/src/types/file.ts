export type FileCategory = "all" | "html" | "image" | "code" | "document" | "data";

export interface SessionFile {
  id: string;
  session_id: string;
  user_id: string;
  task_id?: string | null;
  file_name: string;
  file_path: string;
  file_size: number;
  mime_type: string;
  category: "html" | "image" | "code" | "document" | "data" | string;
  storage_type: string;
  preview_url: string;
  download_url: string;
  created_at: string;
  updated_at: string;
}

export interface FileListResponse {
  total: number;
  items: SessionFile[];
}
