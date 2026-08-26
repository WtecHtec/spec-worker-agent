import JSZip from "jszip";
import { api, SANDBOX_BASE } from "@/lib/api";

/**
 * 批量拉取指定会话的所有产出文件，打包为 .zip 并触发浏览器下载
 */
export async function downloadSessionFilesAsZip(
  sessionId: string,
  token: string,
  zipFileName: string = `webcontainer-project-${sessionId.slice(0, 8)}.zip`
): Promise<void> {
  const zip = new JSZip();
  const res = await api.getSessionFiles(sessionId, token);
  const sessionFiles = res.items || [];

  if (sessionFiles.length === 0) {
    throw new Error("当前会话暂无文件可供打包下载");
  }

  for (const f of sessionFiles) {
    try {
      const rawSandboxUrl = `${SANDBOX_BASE}/fs/raw?path=${encodeURIComponent(
        f.file_path.replace(/^\.?\//, "")
      )}&session_id=${encodeURIComponent(sessionId)}`;

      let content = "";
      const rawResp = await fetch(rawSandboxUrl);
      if (rawResp.ok) {
        content = await rawResp.text();
      } else {
        const fileStreamUrl = api.getFilePreviewUrl(sessionId, f.id, token);
        const fileResp = await fetch(fileStreamUrl);
        if (fileResp.ok) {
          content = await fileResp.text();
        }
      }

      if (content && !content.startsWith("Error: Failed to stream")) {
        const cleanPath = f.file_path.replace(/^\.?\//, "");
        zip.file(cleanPath, content);
      }
    } catch (err) {
      console.warn(`Failed to package ${f.file_path} into zip:`, err);
    }
  }

  const blob = await zip.generateAsync({ type: "blob" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = zipFileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
