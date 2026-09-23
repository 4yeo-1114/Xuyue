import { useState, useEffect, useRef, useMemo, Fragment } from "react";
import { toast } from "sonner";
import { API_PREFIX } from "@/config/api";
import { gradingImageUrl } from "@/services/gradingApi";
import {
  listResourceFolders,
  createResourceFolder,
  deleteResourceFolder,
  listResourceFiles,
  uploadResourceFiles,
  deleteResourceFile,
  renameResourceFile,
  sendResourcesEmail,
  getAuthToken,
  getAllUsers,
  type ResourceFolder,
  type ResourceFile,
} from "@/services/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Check, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Folder,
  FolderPlus,
  Search,
  Upload,
  Download,
  Mail,
  Trash2,
  Edit2,
  File as FileIcon,
  FileText,
  FileImage,
  FileVideo,
  FileAudio,
  FileSpreadsheet,
  Presentation,
  MoreVertical,
  Loader2,
  Eye,
  ChevronRight,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLocale } from "@/contexts/LocaleContext";
import { useAdminAuth } from "@/hooks/useAdminAuth";

function getFileIcon(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  if (["jpg", "jpeg", "png", "gif", "webp"].includes(ext))
    return <FileImage className="w-8 h-8 text-blue-500" />;
  if (["mp4", "webm", "mov", "avi"].includes(ext))
    return <FileVideo className="w-8 h-8 text-purple-500" />;
  if (["mp3", "wav", "ogg"].includes(ext))
    return <FileAudio className="w-8 h-8 text-yellow-500" />;
  if (["doc", "docx"].includes(ext))
    return <FileText className="w-8 h-8 text-blue-600" />;
  if (["xls", "xlsx"].includes(ext))
    return <FileSpreadsheet className="w-8 h-8 text-green-600" />;
  if (["ppt", "pptx"].includes(ext))
    return <Presentation className="w-8 h-8 text-orange-500" />;
  if (["txt", "md"].includes(ext))
    return <FileText className="w-8 h-8 text-gray-500" />;
  return <FileIcon className="w-8 h-8 text-gray-400" />;
}

function getFileTypeCategory(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  if (["jpg", "jpeg", "png", "gif", "webp"].includes(ext)) return "image";
  if (["mp4", "webm", "mov", "avi"].includes(ext)) return "video";
  if (["mp3", "wav", "ogg"].includes(ext)) return "audio";
  if (["doc", "docx"].includes(ext)) return "word";
  if (["xls", "xlsx"].includes(ext)) return "excel";
  if (["ppt", "pptx"].includes(ext)) return "ppt";
  if (["txt", "md"].includes(ext)) return "txt";
  return "other";
}

function formatBytes(bytes: number, decimals = 2) {
  if (!+bytes) return "0 Bytes";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

/** 文件网格单页展示数量（增量渲染，避免一次性渲染全部文件） */
const FILE_PAGE_SIZE = 30;

/** 把多级相对路径逐段编码、保留「/」（如「一年级/语文」）。 */
function encodePath(p: string) {
  return p.split("/").map(encodeURIComponent).join("/");
}

export function ResourceLibPage() {
  const { t } = useLocale();
  const { isAdmin } = useAdminAuth();

  // 竞态守卫：切换文件夹时丢弃过期响应，避免快速切换渲染错文件列表
  const foldersReqSeqRef = useRef(0);
  const filesReqSeqRef = useRef(0);

  const [folders, setFolders] = useState<ResourceFolder[]>([]);
  const [currentPath, setCurrentPath] = useState<string[]>([]);
  const [files, setFiles] = useState<ResourceFile[]>([]);

  // 当前层级完整路径（如「一年级/语文」），空串 = 根目录
  const activePath = currentPath.join("/");
  const currentName = currentPath.length
    ? currentPath[currentPath.length - 1]
    : "";
  const [loadingFolders, setLoadingFolders] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);

  const [folderSearch, setFolderSearch] = useState("");
  const [fileSearch, setFileSearch] = useState("");
  const [fileTypeFilter, setFileTypeFilter] = useState("all");
  const [visibleCount, setVisibleCount] = useState(FILE_PAGE_SIZE);

  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());

  // Modals
  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");

  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [renameOpen, setRenameOpen] = useState(false);
  const [fileToRename, setFileToRename] = useState("");
  const [newFileName, setNewFileName] = useState("");

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewFile, setPreviewFile] = useState<ResourceFile | null>(null);

  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailTargetType, setEmailTargetType] = useState<"self" | "others">(
    "self",
  );
  const [emailUserComboboxOpen, setEmailUserComboboxOpen] = useState(false);
  const [targetEmailInput, setTargetEmailInput] = useState("");
  const [selectedUserObj, setSelectedUserObj] = useState<{
    id: string;
    email: string;
    display_name?: string | null;
  } | null>(null);
  const [usersList, setUsersList] = useState<
    { id: string; email: string; display_name?: string | null }[]
  >([]);
  const [loadingUsers, setLoadingUsers] = useState(false);

  // Batch action state
  const [batchMode, setBatchMode] = useState<
    "none" | "download" | "delete" | "email"
  >("none");

  const fetchUsersList = async () => {
    // getAllUsers 是 admin-only 接口，普通教师必然 403；仅管理员才尝试拉取
    if (!isAdmin) return;
    setLoadingUsers(true);
    try {
      const users = await getAllUsers();
      // Keep all users in the list
      setUsersList(users);
    } catch (err) {
      toast.error(t("resourceLib.toast.fetchUsersFailed"));
    } finally {
      setLoadingUsers(false);
    }
  };

  useEffect(() => {
    if (
      emailModalOpen &&
      emailTargetType === "others" &&
      usersList.length === 0 &&
      isAdmin
    ) {
      fetchUsersList();
    }
  }, [emailModalOpen, emailTargetType, isAdmin]);

  const fetchFolders = async () => {
    const seq = ++foldersReqSeqRef.current;
    setLoadingFolders(true);
    try {
      const res = await listResourceFolders(currentPath.join("/"));
      if (seq !== foldersReqSeqRef.current) return; // 过期响应丢弃
      setFolders(res);
    } catch (err) {
      if (seq !== foldersReqSeqRef.current) return; // 过期响应丢弃
      toast.error(t("resourceLib.toast.fetchFoldersFailed"));
    } finally {
      if (seq === foldersReqSeqRef.current) setLoadingFolders(false);
    }
  };

  const fetchFiles = async (folder: string) => {
    const seq = ++filesReqSeqRef.current;
    setLoadingFiles(true);
    try {
      const res = await listResourceFiles(folder);
      if (seq !== filesReqSeqRef.current) return; // 过期响应丢弃，避免快速切换文件夹渲染错列表
      setFiles(res);
      setSelectedFiles(new Set());
    } catch (err) {
      if (seq !== filesReqSeqRef.current) return; // 过期响应丢弃
      toast.error(t("resourceLib.toast.fetchFilesFailed"));
    } finally {
      if (seq === filesReqSeqRef.current) setLoadingFiles(false);
    }
  };

  useEffect(() => {
    fetchFolders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPath]);

  useEffect(() => {
    fetchFiles(currentPath.join("/"));
    setBatchMode("none");
    setSelectedFiles(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPath]);

  // 切换层级或筛选条件后重置「加载更多」分页
  useEffect(() => {
    setVisibleCount(FILE_PAGE_SIZE);
  }, [currentPath, fileSearch, fileTypeFilter]);

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) {
      toast.error(t("resourceLib.toast.folderNameRequired"));
      return;
    }
    try {
      await createResourceFolder(newFolderName.trim(), activePath);
      toast.success(t("resourceLib.toast.createSuccess"));
      setCreateFolderOpen(false);
      setNewFolderName("");
      fetchFolders();
    } catch (err: any) {
      toast.error(err.message || t("resourceLib.toast.createFailed"));
    }
  };

  const handleUploadFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    setUploading(true);
    try {
      const fileArray = Array.from(e.target.files);
      await uploadResourceFiles(activePath, fileArray);
      toast.success(t("resourceLib.toast.uploadSuccess"));
      fetchFiles(activePath);
    } catch (err: any) {
      toast.error(err.message || t("resourceLib.toast.uploadFailed"));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDeleteFile = async (fileName: string) => {
    if (!confirm(t("resourceLib.toast.deleteConfirm", { name: fileName })))
      return;
    try {
      await deleteResourceFile(activePath, fileName);
      toast.success(t("resourceLib.toast.deleteSuccess"));
      fetchFiles(activePath);
    } catch (err: any) {
      toast.error(err.message || t("resourceLib.toast.deleteFailed"));
    }
  };

  const handleRenameFile = async () => {
    if (!fileToRename || !newFileName.trim()) return;
    try {
      await renameResourceFile(activePath, fileToRename, newFileName.trim());
      toast.success(t("resourceLib.toast.renameSuccess"));
      setRenameOpen(false);
      fetchFiles(activePath);
    } catch (err: any) {
      toast.error(err.message || t("resourceLib.toast.renameFailed"));
    }
  };

  const handleDeleteFolder = async (folderName: string) => {
    if (
      !confirm(t("resourceLib.toast.deleteFolderConfirm", { name: folderName }))
    )
      return;
    try {
      const fullPath = activePath ? `${activePath}/${folderName}` : folderName;
      await deleteResourceFolder(fullPath);
      toast.success(t("resourceLib.toast.deleteFolderSuccess"));
      fetchFolders();
    } catch (err: any) {
      toast.error(err.message || t("resourceLib.toast.deleteFolderFailed"));
    }
  };

  const handleSendEmailClick = () => {
    if (batchMode !== "email") {
      // 普通教师无全量用户接口，「发送给他人」选择器已对非管理员隐藏
      if (!isAdmin) {
        toast.info(t("resourceLib.toast.sendToOthersAdminOnly"));
      }
      setBatchMode("email");
      setSelectedFiles(new Set());
      return;
    }
    if (selectedFiles.size === 0) {
      toast.error(t("resourceLib.toast.selectFilesToSend"));
      return;
    }
    setTargetEmailInput("");
    setSelectedUserObj(null);
    setEmailTargetType("self");
    setEmailModalOpen(true);
  };

  const executeSendEmail = async () => {
    // 非管理员没有全量用户选择器，仅允许发送给自己
    if (emailTargetType === "others" && !isAdmin) {
      toast.error(t("resourceLib.toast.sendToOthersAdminOnly"));
      setEmailTargetType("self");
      return;
    }
    setSendingEmail(true);
    try {
      const targetEmail =
        emailTargetType === "others" ? targetEmailInput : undefined;
      const res = await sendResourcesEmail(
        activePath,
        Array.from(selectedFiles),
        targetEmail,
      );
      toast.success(
        t("resourceLib.toast.sendSuccess", { email: res.to_email }),
      );
      setSelectedFiles(new Set());
      setEmailModalOpen(false);
      setSelectedUserObj(null);
      setBatchMode("none");
    } catch (err: any) {
      toast.error(err.message || t("resourceLib.toast.sendFailed"));
    } finally {
      setSendingEmail(false);
    }
  };

  const executeDownload = async (
    url: string,
    filename: string,
    method: string = "GET",
    body?: any,
  ) => {
    try {
      const token = (await getAuthToken()) || "";
      // 鉴权走 Authorization Header，不再把长期 JWT 拼进 URL query（避免 token 进入 URL 历史/日志/Referer）
      const downloadUrl = url;

      const options: RequestInit = {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
        },
      };

      if (body) {
        options.headers = {
          ...options.headers,
          "Content-Type": "application/json",
        };
        options.body = JSON.stringify(body);
      }

      const response = await fetch(downloadUrl, options);
      if (!response.ok) {
        throw new Error(
          t("resourceLib.toast.downloadFailed", { status: response.status }),
        );
      }

      // 获取 Blob 数据
      const blob = await response.blob();

      // 尝试从 Content-Disposition 提取真正的文件名，如果没有则使用备用名称
      let actualFilename = filename;
      const disposition = response.headers.get("Content-Disposition");
      if (disposition && disposition.indexOf("filename*=utf-8''") !== -1) {
        const matches = /filename\*\=utf-8''([^;]+)/.exec(disposition);
        if (matches != null && matches[1]) {
          actualFilename = decodeURIComponent(matches[1]);
        }
      }

      // 动态创建 a 标签触发下载
      const windowUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.style.display = "none";
      a.href = windowUrl;
      a.download = actualFilename;
      document.body.appendChild(a);
      a.click();

      // 立即移除临时 a 标签；Blob URL 延迟到下载读取完成后 revoke，避免下载被中断
      document.body.removeChild(a);
      window.setTimeout(() => {
        window.URL.revokeObjectURL(windowUrl);
      }, 1000);
    } catch (err: any) {
      toast.error(err.message || t("resourceLib.toast.downloadError"));
    }
  };

  const handleDownloadFolderZip = async () => {
    if (batchMode !== "download") {
      setBatchMode("download");
      setSelectedFiles(new Set());
      return;
    }
    if (selectedFiles.size === 0) {
      toast.error(t("resourceLib.toast.selectFilesToDownload"));
      return;
    }

    const url = `${API_PREFIX}/resources/folders/${encodePath(activePath)}/download-zip`;
    toast.info(t("resourceLib.toast.packaging"));
    await executeDownload(url, `${currentName || "资源库"}.zip`, "POST", {
      files: Array.from(selectedFiles),
    });

    setBatchMode("none");
    setSelectedFiles(new Set());
  };

  const handleBatchDelete = async () => {
    if (batchMode !== "delete") {
      setBatchMode("delete");
      setSelectedFiles(new Set());
      return;
    }
    if (selectedFiles.size === 0) {
      toast.error(t("resourceLib.toast.selectFilesToDelete"));
      return;
    }
    if (
      !confirm(
        t("resourceLib.toast.batchDeleteConfirm", {
          count: selectedFiles.size,
        }),
      )
    )
      return;

    try {
      // API currently only supports deleting one file at a time, so we loop
      const fileNames = Array.from(selectedFiles);
      for (const fileName of fileNames) {
        await deleteResourceFile(activePath, fileName);
      }
      toast.success(
        t("resourceLib.toast.batchDeleteSuccess", { count: fileNames.length }),
      );
      setBatchMode("none");
      setSelectedFiles(new Set());
      fetchFiles(activePath);
    } catch (err: any) {
      // 中途失败：刷新文件列表（已删文件不再展示）、清空选择、退出批量模式，
      // 避免已删文件仍显示且保持选中
      toast.error(err.message || t("resourceLib.toast.batchDeleteFailed"));
      fetchFiles(activePath);
      setSelectedFiles(new Set());
      setBatchMode("none");
    }
  };

  const toggleFileSelection = (fileName: string) => {
    if (batchMode === "none") return;
    const next = new Set(selectedFiles);
    if (next.has(fileName)) {
      next.delete(fileName);
    } else {
      next.add(fileName);
    }
    setSelectedFiles(next);
  };

  const filteredFolders = useMemo(() => {
    return folders.filter((f) =>
      f.name.toLowerCase().includes(folderSearch.toLowerCase()),
    );
  }, [folders, folderSearch]);

  const filteredFiles = useMemo(() => {
    return files.filter((f) => {
      const matchSearch = f.name
        .toLowerCase()
        .includes(fileSearch.toLowerCase());
      const matchType =
        fileTypeFilter === "all" ||
        getFileTypeCategory(f.name) === fileTypeFilter;
      return matchSearch && matchType;
    });
  }, [files, fileSearch, fileTypeFilter]);

  const allSelected =
    filteredFiles.length > 0 && selectedFiles.size === filteredFiles.length;

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedFiles(new Set());
    } else {
      setSelectedFiles(new Set(filteredFiles.map((f) => f.name)));
    }
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* Left Sidebar: Folders */}
      <Card className="w-64 flex flex-col shrink-0 overflow-hidden">
        <CardHeader className="px-4 py-3 border-b">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">
              {t("resourceLib.page.foldersTitle")}
            </CardTitle>
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("resourceLib.page.createFolder")}
              className="h-8 w-8"
              onClick={() => setCreateFolderOpen(true)}
            >
              <FolderPlus className="h-4 w-4" />
            </Button>
          </div>
          <div className="relative mt-2">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder={t("resourceLib.page.searchFolders")}
              className="h-8 pl-8 text-xs"
              value={folderSearch}
              onChange={(e) => setFolderSearch(e.target.value)}
            />
          </div>
        </CardHeader>
        <ScrollArea className="flex-1 p-2">
          {loadingFolders ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              {t("common.loading")}
            </div>
          ) : filteredFolders.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              {t("resourceLib.page.noFolders")}
            </div>
          ) : (
            <div className="space-y-1">
              {filteredFolders.map((folder) => (
                <div
                  key={folder.name}
                  role="button"
                  tabIndex={0}
                  aria-label={t("resourceLib.page.openFolder", {
                    name: folder.name,
                  })}
                  className={`group flex items-center justify-between px-3 py-2 rounded-md cursor-pointer transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring hover:bg-muted text-foreground`}
                  onClick={() => setCurrentPath((p) => [...p, folder.name])}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setCurrentPath((p) => [...p, folder.name]);
                    }
                  }}
                >
                  <div className="flex items-center gap-2 truncate">
                    <Folder className="h-4 w-4 shrink-0 fill-muted" />
                    <span className="truncate text-sm">{folder.name}</span>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      asChild
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t("resourceLib.page.moreActions", {
                          name: folder.name,
                        })}
                        className="h-6 w-6 opacity-100 transition-opacity"
                      >
                        <MoreVertical className="h-3.5 w-3.5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        className="text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteFolder(folder.name);
                        }}
                      >
                        <Trash2 className="h-4 w-4 mr-2" />{" "}
                        {t("resourceLib.page.deleteFolder")}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </Card>

      {/* Right Content: Files */}
      <Card className="flex-1 flex flex-col overflow-hidden">
        <CardHeader className="px-4 py-3 border-b space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <Folder className="h-5 w-5 text-primary fill-primary/20 shrink-0" />
              <nav className="flex items-center gap-0.5 text-sm min-w-0" aria-label="breadcrumb">
                <button
                  type="button"
                  onClick={() => setCurrentPath([])}
                  className={`shrink-0 rounded px-1.5 py-0.5 transition-colors ${
                    currentPath.length === 0
                      ? "font-semibold text-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted"
                  }`}
                >
                  {t("resourceLib.page.rootFolder")}
                </button>
                {currentPath.map((seg, i) => (
                  <Fragment key={`${seg}-${i}`}>
                    <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <button
                      type="button"
                      onClick={() => setCurrentPath(currentPath.slice(0, i + 1))}
                      className={`max-w-[9rem] truncate rounded px-1.5 py-0.5 transition-colors ${
                        i === currentPath.length - 1
                          ? "font-semibold text-foreground"
                          : "text-muted-foreground hover:text-foreground hover:bg-muted"
                      }`}
                    >
                      {seg}
                    </button>
                  </Fragment>
                ))}
              </nav>
            </div>
                <div className="flex items-center gap-2">
                  {batchMode === "none" ? (
                    <>
                      <input
                        type="file"
                        multiple
                        className="hidden"
                        ref={fileInputRef}
                        onChange={handleUploadFiles}
                      />
                      <Button
                        size="sm"
                        className="h-8 gap-1.5"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploading}
                      >
                        {uploading ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Upload className="h-3.5 w-3.5" />
                        )}
                        {t("resourceLib.page.uploadFiles")}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 gap-1.5"
                        onClick={handleDownloadFolderZip}
                        disabled={files.length === 0}
                      >
                        <Download className="h-3.5 w-3.5" />
                        {t("resourceLib.page.downloadZip")}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 gap-1.5"
                        onClick={handleSendEmailClick}
                        disabled={files.length === 0}
                      >
                        <Mail className="h-3.5 w-3.5" />
                        {t("resourceLib.page.sendEmail")}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 gap-1.5 text-destructive hover:text-destructive"
                        onClick={handleBatchDelete}
                        disabled={files.length === 0}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        {t("resourceLib.page.batchDelete")}
                      </Button>
                    </>
                  ) : (
                    <>
                      <div className="text-sm font-medium mr-2">
                        {t("resourceLib.page.selectedCount", {
                          count: selectedFiles.size,
                        })}
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8"
                        onClick={() => {
                          setBatchMode("none");
                          setSelectedFiles(new Set());
                        }}
                      >
                        {t("common.cancel")}
                      </Button>
                      {batchMode === "download" && (
                        <Button
                          size="sm"
                          className="h-8 gap-1.5"
                          onClick={handleDownloadFolderZip}
                        >
                          <Download className="h-3.5 w-3.5" />
                          {t("resourceLib.page.confirmDownload")}
                        </Button>
                      )}
                      {batchMode === "email" && (
                        <Button
                          size="sm"
                          className="h-8 gap-1.5"
                          onClick={handleSendEmailClick}
                        >
                          <Mail className="h-3.5 w-3.5" />
                          {t("resourceLib.page.confirmSend")}
                        </Button>
                      )}
                      {batchMode === "delete" && (
                        <Button
                          size="sm"
                          variant="destructive"
                          className="h-8 gap-1.5"
                          onClick={handleBatchDelete}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          {t("resourceLib.page.confirmDelete")}
                        </Button>
                      )}
                    </>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="relative w-64">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder={t("resourceLib.page.searchFiles")}
                    className="h-8 pl-8 text-xs"
                    value={fileSearch}
                    onChange={(e) => setFileSearch(e.target.value)}
                  />
                </div>
                <Select
                  value={fileTypeFilter}
                  onValueChange={setFileTypeFilter}
                >
                  <SelectTrigger className="h-8 w-32 text-xs">
                    <SelectValue
                      placeholder={t("resourceLib.page.allFormats")}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">
                      {t("resourceLib.page.allFormats")}
                    </SelectItem>
                    <SelectItem value="word">
                      {t("resourceLib.fileType.word")}
                    </SelectItem>
                    <SelectItem value="excel">
                      {t("resourceLib.fileType.excel")}
                    </SelectItem>
                    <SelectItem value="ppt">
                      {t("resourceLib.fileType.ppt")}
                    </SelectItem>
                    <SelectItem value="image">
                      {t("resourceLib.fileType.image")}
                    </SelectItem>
                    <SelectItem value="video">
                      {t("resourceLib.fileType.video")}
                    </SelectItem>
                    <SelectItem value="audio">
                      {t("resourceLib.fileType.audio")}
                    </SelectItem>
                    <SelectItem value="txt">
                      {t("resourceLib.fileType.txt")}
                    </SelectItem>
                    <SelectItem value="other">
                      {t("resourceLib.fileType.other")}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>

            {batchMode !== "none" && (
              <div className="px-4 py-2 border-b bg-muted/20 flex items-center gap-3">
                <Checkbox
                  checked={allSelected}
                  onCheckedChange={toggleSelectAll}
                  id="select-all"
                />
                <label
                  htmlFor="select-all"
                  className="text-xs font-medium cursor-pointer"
                >
                  {t("common.selectAll")}
                </label>
                <span className="text-xs text-muted-foreground ml-auto">
                  {t("resourceLib.page.totalFiles", {
                    count: filteredFiles.length,
                  })}
                </span>
              </div>
            )}

            <ScrollArea className="flex-1 p-4 bg-muted/10">
              {loadingFiles ? (
                <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin mr-2" />{" "}
                  {t("resourceLib.page.loadingFiles")}
                </div>
              ) : filteredFiles.length === 0 ? (
                <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
                  {t("resourceLib.page.noMatchingFiles")}
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                    {filteredFiles.slice(0, visibleCount).map((file) => {
                      const isSelected = selectedFiles.has(file.name);
                      return (
                        <Card
                          key={file.name}
                          role="button"
                          tabIndex={0}
                          aria-label={
                            batchMode !== "none"
                              ? t("resourceLib.page.selectFile", {
                                  name: file.name,
                                })
                              : t("resourceLib.page.preview")
                          }
                          className={`overflow-hidden transition-all hover:shadow-md cursor-pointer group outline-none focus-visible:ring-2 focus-visible:ring-ring ${isSelected && batchMode !== "none" ? "border-primary ring-1 ring-primary/20" : ""}`}
                          // 非批量模式：点击卡片直接预览（原先这里既无预览又无选中，
                          // 点击等于无反应，只能绕到右上角「⋯ → 预览」）；
                          // 批量模式：点击切换选中。
                          onClick={() => {
                            if (batchMode === "none") {
                              setPreviewFile(file);
                              setPreviewOpen(true);
                            } else {
                              toggleFileSelection(file.name);
                            }
                          }}
                          onKeyDown={(e) => {
                            if (e.key !== "Enter" && e.key !== " ") return;
                            e.preventDefault();
                            if (batchMode === "none") {
                              setPreviewFile(file);
                              setPreviewOpen(true);
                            } else {
                              toggleFileSelection(file.name);
                            }
                          }}
                        >
                          <div className="h-28 bg-muted/30 flex items-center justify-center relative">
                            {batchMode !== "none" && (
                              <div
                                className="absolute top-2 left-2"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <Checkbox
                                  checked={isSelected}
                                  onCheckedChange={() =>
                                    toggleFileSelection(file.name)
                                  }
                                  aria-label={t("resourceLib.page.selectFile", {
                                    name: file.name,
                                  })}
                                />
                              </div>
                            )}
                            <div
                              className="absolute top-2 right-2 opacity-100 transition-opacity"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <Button
                                    variant="secondary"
                                    size="icon"
                                    aria-label={t(
                                      "resourceLib.page.moreActions",
                                      { name: file.name },
                                    )}
                                    className="h-6 w-6 bg-background/80 hover:bg-background"
                                  >
                                    <MoreVertical className="h-3.5 w-3.5" />
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end">
                                  <DropdownMenuItem
                                    onClick={() => {
                                      setPreviewFile(file);
                                      setPreviewOpen(true);
                                    }}
                                  >
                                    <Eye className="h-4 w-4 mr-2" />{" "}
                                    {t("resourceLib.page.preview")}
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    onClick={async (e) => {
                                      e.stopPropagation();
                                      const url = `${API_PREFIX}/resources/folders/${encodePath(activePath)}/files/${encodeURIComponent(file.name)}/download`;
                                      toast.info(
                                        t("resourceLib.toast.downloading", {
                                          name: file.name,
                                        }),
                                      );
                                      await executeDownload(url, file.name);
                                    }}
                                  >
                                    <Download className="h-4 w-4 mr-2" />{" "}
                                    {t("common.download")}
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    onClick={() => {
                                      setFileToRename(file.name);
                                      setNewFileName(file.name);
                                      setRenameOpen(true);
                                    }}
                                  >
                                    <Edit2 className="h-4 w-4 mr-2" />{" "}
                                    {t("resourceLib.page.rename")}
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    className="text-destructive"
                                    onClick={() => handleDeleteFile(file.name)}
                                  >
                                    <Trash2 className="h-4 w-4 mr-2" />{" "}
                                    {t("common.delete")}
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </div>
                            {file.cover_url ? (
                              <div className="absolute inset-0 flex items-center justify-center bg-muted/10 p-2">
                                <img
                                  src={gradingImageUrl(file.cover_url)}
                                  alt={file.name}
                                  className="max-w-full max-h-full object-contain rounded-sm shadow-sm"
                                  loading="lazy"
                                />
                              </div>
                            ) : (
                              getFileIcon(file.name)
                            )}
                          </div>
                          <div className="p-3 border-t bg-background">
                            <div
                              className="text-sm font-medium truncate mb-1"
                              title={file.name}
                            >
                              {file.name}
                            </div>
                            <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                              <span>
                                {new Date(
                                  file.modified_at,
                                ).toLocaleDateString()}
                              </span>
                              <span>{formatBytes(file.size)}</span>
                            </div>
                          </div>
                        </Card>
                      );
                    })}
                  </div>
                  {filteredFiles.length > visibleCount && (
                    <div className="flex justify-center mt-4">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          setVisibleCount((c) => c + FILE_PAGE_SIZE)
                        }
                      >
                        {t("resourceLib.page.loadMore", {
                          count: Math.min(
                            FILE_PAGE_SIZE,
                            filteredFiles.length - visibleCount,
                          ),
                        })}
                      </Button>
                    </div>
                  )}
                </>
              )}
            </ScrollArea>
      </Card>

      {/* Dialogs */}
      <Dialog open={createFolderOpen} onOpenChange={setCreateFolderOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("resourceLib.page.createFolder")}</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Input
              placeholder={t("resourceLib.page.folderNamePlaceholder")}
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreateFolder()}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCreateFolderOpen(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button onClick={handleCreateFolder}>
              {t("resourceLib.page.confirmCreate")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("resourceLib.page.renameFile")}</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Input
              placeholder={t("resourceLib.page.newFileNamePlaceholder")}
              value={newFileName}
              onChange={(e) => setNewFileName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleRenameFile()}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={handleRenameFile}>
              {t("resourceLib.page.confirmModify")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="sm:max-w-4xl h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="truncate pr-8">
              {previewFile?.name}
            </DialogTitle>
          </DialogHeader>
          <div className="flex-1 bg-muted/30 rounded-md overflow-hidden flex items-center justify-center relative">
            {previewFile &&
              (getFileTypeCategory(previewFile.name) === "image" ? (
                <img
                  src={gradingImageUrl(previewFile.url)}
                  alt={previewFile.name}
                  className="max-w-full max-h-full object-contain"
                />
              ) : getFileTypeCategory(previewFile.name) === "video" ? (
                <video
                  src={gradingImageUrl(previewFile.url)}
                  controls
                  className="max-w-full max-h-full outline-none"
                />
              ) : getFileTypeCategory(previewFile.name) === "audio" ? (
                <audio
                  src={gradingImageUrl(previewFile.url)}
                  controls
                  className="w-full max-w-md"
                />
              ) : ["word", "excel", "ppt"].includes(
                  getFileTypeCategory(previewFile.name),
                ) ? (
                <div className="flex flex-col items-center justify-center text-muted-foreground p-8 text-center">
                  <div className="scale-150 mb-6">
                    {getFileIcon(previewFile.name)}
                  </div>
                  <p className="mb-2 text-base font-medium text-foreground">
                    {t("resourceLib.page.previewUnsupported", {
                      type: t(
                        `resourceLib.fileType.${getFileTypeCategory(previewFile.name)}`,
                      ),
                    })}
                  </p>
                  <p className="mb-6 text-sm text-muted-foreground">
                    {t("resourceLib.page.previewDownloadHint")}
                  </p>
                  <Button
                    onClick={async () => {
                      const url = `${API_PREFIX}/resources/folders/${encodePath(activePath)}/files/${encodeURIComponent(previewFile.name)}/download`;
                      toast.info(
                        t("resourceLib.toast.downloading", {
                          name: previewFile.name,
                        }),
                      );
                      await executeDownload(url, previewFile.name);
                    }}
                  >
                    <Download className="h-4 w-4 mr-2" />{" "}
                    {t("resourceLib.page.downloadNow")}
                  </Button>
                </div>
              ) : (
                <iframe
                  src={gradingImageUrl(previewFile.url)}
                  className="w-full h-full border-0 bg-white"
                />
              ))}
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={emailModalOpen} onOpenChange={setEmailModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("common.emailSend.title")}</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Tabs
              value={emailTargetType}
              onValueChange={(v) => setEmailTargetType(v as "self" | "others")}
              className="w-full"
            >
              <TabsList
                className={`grid w-full mb-4 ${isAdmin ? "grid-cols-2" : "grid-cols-1"}`}
              >
                <TabsTrigger value="self">
                  {t("common.emailSend.sendToSelf")}
                </TabsTrigger>
                {isAdmin && (
                  <TabsTrigger value="others">
                    {t("common.emailSend.sendToOthers")}
                  </TabsTrigger>
                )}
              </TabsList>

              <TabsContent value="self" className="mt-0">
                <div className="text-sm text-muted-foreground p-4 bg-muted/30 rounded-md">
                  <p>{t("common.emailSend.selfHint")}</p>
                  <p className="mt-2 text-xs">
                    {t("common.emailSend.selectedCount", {
                      count: selectedFiles.size,
                    })}
                  </p>
                </div>
              </TabsContent>

              {isAdmin && (
                <TabsContent value="others" className="mt-0 space-y-4">
                  <div className="space-y-2">
                    <label className="text-sm font-medium">
                      {t("common.emailSend.searchUsers")}
                    </label>
                    <Popover
                      open={emailUserComboboxOpen}
                      onOpenChange={setEmailUserComboboxOpen}
                    >
                      <PopoverTrigger asChild>
                        <Button
                          variant="outline"
                          role="combobox"
                          aria-expanded={emailUserComboboxOpen}
                          className="w-full justify-between font-normal"
                          disabled={loadingUsers}
                        >
                          {selectedUserObj
                            ? `${selectedUserObj.display_name || selectedUserObj.email.split("@")[0]} (${selectedUserObj.email})`
                            : loadingUsers
                              ? t("common.emailSend.loadingUsers")
                              : t("common.emailSend.searchUserPlaceholder")}
                          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-[380px] p-0" align="start">
                        <Command>
                          <CommandInput
                            placeholder={t("common.emailSend.searchUserInput")}
                          />
                          <CommandList>
                            <CommandEmpty>
                              {t("common.emailSend.userNotFound")}
                            </CommandEmpty>
                            <CommandGroup>
                              {usersList.map((u) => (
                                <CommandItem
                                  key={u.id}
                                  value={`${u.display_name || u.email.split("@")[0]} ${u.email}`}
                                  onSelect={() => {
                                    setSelectedUserObj(u);
                                    setTargetEmailInput(u.email);
                                    setEmailUserComboboxOpen(false);
                                  }}
                                >
                                  <Check
                                    className={cn(
                                      "mr-2 h-4 w-4",
                                      selectedUserObj?.id === u.id
                                        ? "opacity-100"
                                        : "opacity-0",
                                    )}
                                  />
                                  {u.display_name || u.email.split("@")[0]}
                                  <span className="ml-2 text-muted-foreground">
                                    ({u.email})
                                  </span>
                                </CommandItem>
                              ))}
                            </CommandGroup>
                          </CommandList>
                        </Command>
                      </PopoverContent>
                    </Popover>
                  </div>

                  <div className="relative flex items-center py-2">
                    <div className="flex-grow border-t border-border"></div>
                    <span className="flex-shrink-0 mx-4 text-muted-foreground text-xs">
                      {t("common.emailSend.orManualInput")}
                    </span>
                    <div className="flex-grow border-t border-border"></div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium">
                      {t("common.emailSend.emailAddress")}
                    </label>
                    <Input
                      type="email"
                      placeholder={t("common.emailSend.emailPlaceholder")}
                      value={targetEmailInput}
                      onChange={(e) => {
                        setTargetEmailInput(e.target.value);
                        if (
                          selectedUserObj &&
                          e.target.value !== selectedUserObj.email
                        ) {
                          setSelectedUserObj(null);
                        }
                      }}
                    />
                  </div>
                </TabsContent>
              )}
            </Tabs>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEmailModalOpen(false)}
              disabled={sendingEmail}
            >
              {t("common.cancel")}
            </Button>
            <Button
              onClick={executeSendEmail}
              disabled={
                sendingEmail ||
                (emailTargetType === "others" && !targetEmailInput.trim())
              }
            >
              {sendingEmail ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Mail className="h-4 w-4 mr-2" />
              )}
              {sendingEmail
                ? t("common.emailSend.sending")
                : t("common.emailSend.confirmSend")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
