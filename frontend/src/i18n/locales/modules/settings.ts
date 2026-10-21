import type { TranslationDict } from "../../types";

export const settingsZh: TranslationDict = {
  "settings.personal.title": "个人设置",
  "settings.personal.subtitle": "管理账号名称、联系方式与教学科目",
  "settings.personal.changePassword": "修改密码",
  "settings.personal.basicInfo": "基本信息",
  "settings.personal.basicInfoDesc": "管理您的姓名、账号、手机号与岗位信息",
  "settings.personal.name": "姓名",
  "settings.personal.namePlaceholder": "您的姓名",
  "settings.personal.account": "账号",
  "settings.personal.jobTitle": "岗位信息",
  "settings.personal.jobTitlePlaceholder": "您的岗位（如：五年级数学组长）",
  "settings.personal.phone": "手机号",
  "settings.personal.phoneOptional": "选填",
  "settings.personal.systemRole": "系统角色",
  "settings.personal.noRoles": "暂无角色",
  "settings.personal.personalEmail": "个人邮箱",
  "settings.personal.personalEmailPlaceholder":
    "您的个人邮箱（用于接收系统邮件）",
  "settings.personal.teachingSubject": "教学科目",
  "settings.personal.selectSubject": "选择科目",
  "settings.personal.subjectUnset": "未设置",
  "settings.personal.saveProfile": "保存资料",
  "settings.personal.loginRequired": "请先登录",
  "settings.personal.toast.saved": "资料已保存",
  "settings.personal.toast.saveFailed": "保存失败",
  "settings.personal.toast.oldPwdRequired": "请输入原密码",
  "settings.personal.toast.newPwdMin": "新密码至少6位",
  "settings.personal.toast.pwdMismatch": "两次输入的新密码不一致",
  "settings.personal.toast.pwdChanged": "密码已修改",
  "settings.personal.toast.pwdChangeFailed": "修改失败",
  "settings.personal.pwd.title": "修改密码",
  "settings.personal.pwd.desc": "请先输入原密码，验证通过后即可设置新密码",
  "settings.personal.pwd.old": "原密码",
  "settings.personal.pwd.new": "新密码",
  "settings.personal.pwd.confirm": "确认新密码",
  "settings.personal.pwd.confirmBtn": "确认修改",
  "settings.personal.sendCode": "发送验证码",
  "settings.personal.codePlaceholder": "请输入短信验证码",
  "settings.personal.toast.invalidPhone": "请输入有效的手机号",
  "settings.personal.toast.codeSent": "验证码已发送",
  "settings.personal.toast.codeRequired": "请输入短信验证码",

  "settings.system.title": "系统设置",
  "settings.system.subtitle":
    "存储清理、百度 OCR 鉴权、千问模型 Key 等全局配置",
  "settings.system.loadFailed": "加载失败",
  "settings.system.notSet": "未设置",
  "settings.system.current": "当前：{value}",
  "settings.system.update": "更新",
  "settings.system.baiduToken": "百度 access_token",
  "settings.system.baiduUpdateLabel": "更新 access_token",
  "settings.system.baiduPlaceholder": "粘贴新的 access_token",
  "settings.system.accessTokenRequired": "请输入 access_token",
  "settings.system.baiduUpdated": "access_token 已更新",
  "settings.system.baiduCredentials": "百度 OCR 鉴权",
  "settings.system.baiduApiKey": "百度 API Key",
  "settings.system.baiduSecretKey": "百度 Secret Key",
  "settings.system.baiduApiKeyPlaceholder": "输入 API Key",
  "settings.system.baiduSecretKeyPlaceholder": "输入 Secret Key",
  "settings.system.baiduCredentialsRequired":
    "请输入要更新的 API Key 或 Secret Key",
  "settings.system.baiduCredentialsBothRequired":
    "首次配置必须同时输入 API Key 和 Secret Key",
  "settings.system.baiduCredentialsUpdated": "百度鉴权已更新并验证成功",
  "settings.system.baiduAutoRefreshEnabled":
    "自动刷新已启用，Access Token 过期后会自动更新",
  "settings.system.baiduAutoRefreshDisabled":
    "自动刷新未启用，请配置 API Key 和 Secret Key",
  "settings.system.saveBaiduCredentials": "验证并保存",
  "settings.system.baiduTokenFallback": "兼容方式：手动更新临时 Access Token",
  "settings.system.updateFailed": "更新失败",
  "settings.system.qwenKey": "千问模型 Key",
  "settings.system.qwenApiKey": "DashScope API Key",
  "settings.system.qwenPlaceholder": "粘贴新的 sk-... API Key",
  "settings.system.qwenKeyRequired": "请输入千问 API Key",
  "settings.system.qwenUpdated": "千问配置已更新",
  "settings.system.saveQwen": "保存千问配置",
  "settings.system.requestFailed": "请求失败：{status}",

  "settings.storage.title": "存储清理",
  "settings.storage.description":
    "立即清理无用临时文件、无引用留痕图、扫描未导入文件等；保留试卷、批改记录、错题库及首页快速批改缓存。所有账号均可使用。",
  "settings.storage.lastCleanup": "上次清理：释放 {size}，删除 {count} 个文件",
  "settings.storage.startCleanup": "开始清理",
  "settings.storage.confirmTitle": "确认存储清理？",
  "settings.storage.confirmWillClean": "将自动清理以下内容：",
  "settings.storage.confirmItems":
    "PDF/Word 转换临时文件、系统临时文件、扫描未导入文件、无引用留痕图、AI 诊断缓存、旧版遗留文件。",
  "settings.storage.confirmWillKeep":
    "不会删除：试卷原文件、批改历史、错题库、教学资源库、首页快速批改缓存。",
  "settings.storage.confirmHint":
    "若正在扫描导入，扫描区文件将自动跳过；建议不要在 PDF 转换或批量批改进行中点击清理。",
  "settings.storage.cleaning": "清理中…",
  "settings.storage.toast.freed": "已释放 {size}",
  "settings.storage.toast.deleted": "共删除 {count} 个文件",
  "settings.storage.toast.noJunk": "当前没有可清理的垃圾文件",
  "settings.storage.toast.failed": "清理失败",
  "settings.storage.toast.retry": "请稍后重试",
  "settings.storage.detail.temp": "PDF/Word 转换临时文件",
  "settings.storage.detail.project_temp": "系统临时文件",
  "settings.storage.detail.scan": "扫描仪未导入文件",
  "settings.storage.detail.modify_orphans": "无引用留痕图",
  "settings.storage.detail.home_img_orphans": "首页批改孤儿文件",
  "settings.storage.detail.ai_diagnosis": "AI 诊断缓存",
  "settings.storage.detail.history_legacy": "旧版历史文件",
  "settings.storage.detail.line": "{label}：{files} 个 / {size}",

  "settings.hardware.title": "硬件配置",
  "settings.hardware.subtitle":
    "配置打印机与扫描仪；打印机设置与「开始批改」界面完全同步，所有账号均可使用。",
  "settings.hardware.printer": "打印机",
  "settings.hardware.printerDesc":
    "与批改文件夹顶栏「打印机设置」共用同一套配置，修改后会自动同步。",
  "settings.hardware.refreshList": "刷新列表",
  "settings.hardware.current": "当前：{name}",
  "settings.hardware.systemDefault": "（系统默认）",
  "settings.hardware.scanner": "扫描仪",
  "settings.hardware.scannerDesc":
    "自动检测本机可用扫描仪。批改时使用「扫描导入」将文件写入监测目录后自动归入试卷文件夹。",
  "settings.hardware.detecting": "正在检测扫描仪…",
  "settings.hardware.scannerListFailed": "获取扫描仪列表失败",
  "settings.hardware.noScanner":
    "未检测到可用扫描仪，请确认驱动已安装并已连接设备。",
  "settings.hardware.noScannerHint":
    "（如果是扫描打印一体机，可不用配置此项。）",
  "settings.hardware.manufacturer": "制造商：{name}",
  "settings.hardware.available": "可用",
  "settings.hardware.unavailable": "不可用",

  "settings.access.title": "接入方式",
  "settings.access.subtitle": "无需额外采购设备，三种方式均可开始智能批改",
  "settings.access.enter": "进入",
  "settings.access.photo.title": "手机拍照",
  "settings.access.photo.desc":
    "用手机拍摄作业照片，上传即可 AI 批改，无需任何设备",
  "settings.access.upload.title": "文件上传",
  "settings.access.upload.desc":
    "已有 PDF/Word/图片作业文件，直接上传到批改页面",
  "settings.access.scanner.title": "扫描仪接入",
  "settings.access.scanner.desc":
    "使用已有复合机扫描，自动检测并配置扫描仪后导入批改",
};

export const settingsEn: TranslationDict = {
  "settings.personal.title": "Personal Settings",
  "settings.personal.subtitle":
    "Manage your name, contact info, and teaching subject",
  "settings.personal.changePassword": "Change Password",
  "settings.personal.basicInfo": "Basic Info",
  "settings.personal.basicInfoDesc":
    "Manage your name, account, phone, and job title",
  "settings.personal.name": "Name",
  "settings.personal.namePlaceholder": "Your name",
  "settings.personal.account": "Account",
  "settings.personal.jobTitle": "Job Title",
  "settings.personal.jobTitlePlaceholder": "e.g. Grade 5 Math Lead",
  "settings.personal.phone": "Phone",
  "settings.personal.phoneOptional": "Optional",
  "settings.personal.systemRole": "System Roles",
  "settings.personal.noRoles": "No roles assigned",
  "settings.personal.personalEmail": "Personal Email",
  "settings.personal.personalEmailPlaceholder": "For receiving system emails",
  "settings.personal.teachingSubject": "Teaching Subject",
  "settings.personal.selectSubject": "Select subject",
  "settings.personal.subjectUnset": "Not set",
  "settings.personal.saveProfile": "Save Profile",
  "settings.personal.loginRequired": "Please sign in first",
  "settings.personal.toast.saved": "Profile saved",
  "settings.personal.toast.saveFailed": "Save failed",
  "settings.personal.toast.oldPwdRequired":
    "Please enter your current password",
  "settings.personal.toast.newPwdMin":
    "New password must be at least 6 characters",
  "settings.personal.toast.pwdMismatch": "New passwords do not match",
  "settings.personal.toast.pwdChanged": "Password changed",
  "settings.personal.toast.pwdChangeFailed": "Change failed",
  "settings.personal.pwd.title": "Change Password",
  "settings.personal.pwd.desc":
    "Enter your current password, then set a new one",
  "settings.personal.pwd.old": "Current Password",
  "settings.personal.pwd.new": "New Password",
  "settings.personal.pwd.confirm": "Confirm New Password",
  "settings.personal.pwd.confirmBtn": "Confirm",
  "settings.personal.sendCode": "Send code",
  "settings.personal.codePlaceholder": "Enter SMS code",
  "settings.personal.toast.invalidPhone": "Enter a valid phone number",
  "settings.personal.toast.codeSent": "Code sent",
  "settings.personal.toast.codeRequired": "Enter SMS code",

  "settings.system.title": "System Settings",
  "settings.system.subtitle":
    "Storage cleanup, Baidu OCR credentials, Qwen API key, and other global config",
  "settings.system.loadFailed": "Failed to load",
  "settings.system.notSet": "Not set",
  "settings.system.current": "Current: {value}",
  "settings.system.update": "Update",
  "settings.system.baiduToken": "Baidu access_token",
  "settings.system.baiduUpdateLabel": "Update access_token",
  "settings.system.baiduPlaceholder": "Paste new access_token",
  "settings.system.accessTokenRequired": "Please enter access_token",
  "settings.system.baiduUpdated": "access_token updated",
  "settings.system.baiduCredentials": "Baidu OCR Credentials",
  "settings.system.baiduApiKey": "Baidu API Key",
  "settings.system.baiduSecretKey": "Baidu Secret Key",
  "settings.system.baiduApiKeyPlaceholder": "Enter API Key",
  "settings.system.baiduSecretKeyPlaceholder": "Enter Secret Key",
  "settings.system.baiduCredentialsRequired":
    "Enter the API Key or Secret Key to update",
  "settings.system.baiduCredentialsBothRequired":
    "Enter both API Key and Secret Key for initial setup",
  "settings.system.baiduCredentialsUpdated":
    "Baidu credentials verified and saved",
  "settings.system.baiduAutoRefreshEnabled":
    "Auto refresh is enabled; expired access tokens will be renewed",
  "settings.system.baiduAutoRefreshDisabled":
    "Auto refresh is disabled; configure the API Key and Secret Key",
  "settings.system.saveBaiduCredentials": "Verify and Save",
  "settings.system.baiduTokenFallback":
    "Compatibility option: manually update a temporary access token",
  "settings.system.updateFailed": "Update failed",
  "settings.system.qwenKey": "Qwen Model Key",
  "settings.system.qwenApiKey": "DashScope API Key",
  "settings.system.qwenPlaceholder": "Paste new sk-... API Key",
  "settings.system.qwenKeyRequired": "Please enter Qwen API Key",
  "settings.system.qwenUpdated": "Qwen settings updated",
  "settings.system.saveQwen": "Save Qwen Settings",
  "settings.system.requestFailed": "Request failed: {status}",

  "settings.storage.title": "Storage Cleanup",
  "settings.storage.description":
    "Remove temp files, orphan mark images, unscanned imports, etc. Exam papers, grading records, wrong-question bank, and quick-grade cache are kept. Available to all accounts.",
  "settings.storage.lastCleanup":
    "Last cleanup: freed {size}, deleted {count} file(s)",
  "settings.storage.startCleanup": "Clean Up",
  "settings.storage.confirmTitle": "Confirm storage cleanup?",
  "settings.storage.confirmWillClean": "The following will be removed:",
  "settings.storage.confirmItems":
    "PDF/Word conversion temps, system temps, unscanned imports, orphan mark images, AI diagnosis cache, legacy files.",
  "settings.storage.confirmWillKeep":
    "Will NOT delete: exam originals, grading history, wrong-question bank, teaching resources, quick-grade cache.",
  "settings.storage.confirmHint":
    "Scan-folder files are skipped during active scan import. Avoid cleanup during PDF conversion or batch grading.",
  "settings.storage.cleaning": "Cleaning…",
  "settings.storage.toast.freed": "Freed {size}",
  "settings.storage.toast.deleted": "Deleted {count} file(s)",
  "settings.storage.toast.noJunk": "No junk files to clean",
  "settings.storage.toast.failed": "Cleanup failed",
  "settings.storage.toast.retry": "Please try again later",
  "settings.storage.detail.temp": "PDF/Word conversion temps",
  "settings.storage.detail.project_temp": "System temp files",
  "settings.storage.detail.scan": "Unimported scan files",
  "settings.storage.detail.modify_orphans": "Orphan mark images",
  "settings.storage.detail.home_img_orphans": "Home grading orphan files",
  "settings.storage.detail.ai_diagnosis": "AI diagnosis cache",
  "settings.storage.detail.history_legacy": "Legacy history files",
  "settings.storage.detail.line": "{label}: {files} / {size}",

  "settings.hardware.title": "Hardware",
  "settings.hardware.subtitle":
    "Configure printer and scanner. Printer settings sync with Start Grading. Available to all accounts.",
  "settings.hardware.printer": "Printer",
  "settings.hardware.printerDesc":
    "Shares settings with the printer panel in grading folders; changes sync automatically.",
  "settings.hardware.refreshList": "Refresh",
  "settings.hardware.current": "Current: {name}",
  "settings.hardware.systemDefault": " (system default)",
  "settings.hardware.scanner": "Scanner",
  "settings.hardware.scannerDesc":
    "Auto-detect local scanners. Use Scan Import during grading; files are auto-assigned to paper folders.",
  "settings.hardware.detecting": "Detecting scanners…",
  "settings.hardware.scannerListFailed": "Failed to load scanner list",
  "settings.hardware.noScanner":
    "No scanner detected. Check drivers and device connection.",
  "settings.hardware.noScannerHint":
    "(Skip if using a print-scan combo device.)",
  "settings.hardware.manufacturer": "Manufacturer: {name}",
  "settings.hardware.available": "Available",
  "settings.hardware.unavailable": "Unavailable",

  "settings.access.title": "Access Methods",
  "settings.access.subtitle":
    "No extra hardware needed — start smart grading with any of these methods",
  "settings.access.enter": "Enter",
  "settings.access.photo.title": "Phone Photo",
  "settings.access.photo.desc":
    "Photograph homework with your phone and upload for AI grading — no equipment needed",
  "settings.access.upload.title": "File Upload",
  "settings.access.upload.desc":
    "Upload existing PDF/Word/image homework files directly to the grading page",
  "settings.access.scanner.title": "Scanner Setup",
  "settings.access.scanner.desc":
    "Use an existing copier/scanner — auto-detect and configure, then scan import for grading",
};
