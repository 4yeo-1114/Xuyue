# 叙阅资料库部署：等下载完成 -> 验证本地 -> 清空远程 -> scp 到生产 -> 验证远程。
# 只 Write-Output（由 Start-Process -RedirectStandardOutput 落日志），勿内部写同名文件。
$ErrorActionPreference = 'Continue'

$dlLog    = 'D:\叙阅\叙阅迁移包_20260920\backend\zyk_download.log'
$zyklocal = 'D:\叙阅\叙阅迁移包_20260920\backend\grading_data_all\_shared\zyk_data'
$key      = 'D:\叙阅\id_ed25519_gradebuddy'
$hostAddr = 'root@120.26.101.0'
$remoteBase = '/www/wwwroot/教育项目/批改君/后端/grading_data_all/_shared/zyk_data'

function Log($m) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Output "$ts $m"
}

Log "===== 部署启动 ====="

# 1) 等下载完成（最多 3 小时）
$maxWait = 10800
$waited = 0
while ($waited -lt $maxWait) {
    if (Test-Path $dlLog) {
        if (Select-String -Path $dlLog -Pattern '全部完成' -Quiet) { break }
    }
    Start-Sleep -Seconds 30
    $waited += 30
}
if ($waited -ge $maxWait) { Log "超时：下载 3 小时内未完成，中止部署"; exit 1 }
Log "下载已完成（等待 ${waited}s）"

# 2) 验证本地（新结构：课件PPT/*.pptx + 教学视频/*.pdf）
$pptx = (Get-ChildItem -Path "${zyklocal}\课程教学" -Recurse -Filter '课件PPT-*.pptx' -File -ErrorAction SilentlyContinue | Measure-Object).Count
$vpdf = (Get-ChildItem -Path "${zyklocal}\课程教学" -Recurse -Filter '教学视频-*.pdf' -File -ErrorAction SilentlyContinue | Measure-Object).Count
$zero = (Get-ChildItem -Path "${zyklocal}\课程教学" -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -eq 0 } | Measure-Object).Count
$sz = (Get-ChildItem -Path "${zyklocal}\课程教学" -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
Log ("本地验证 课程教学：PPTX={0} 视频PDF={1} 0字节={2} 体积={3:N2}GB" -f $pptx, $vpdf, $zero, ($sz/1GB))
if ($pptx -lt 3000) { Log "本地 PPTX 数量异常（${pptx}），中止"; exit 1 }

# 3) 清空远程旧数据（避免上次半途 scp 残留的旧 PDF 混合结构）
foreach ($sub in @('课程教学','电子教材')) {
    Log "清空远程 ${sub}"
    ssh -i $key -o StrictHostKeyChecking=no $hostAddr "rm -rf '$remoteBase/${sub}'" 2>&1
}
ssh -i $key -o StrictHostKeyChecking=no $hostAddr "mkdir -p '$remoteBase'" 2>&1

# 4) scp 到生产（课程教学 + 电子教材）
foreach ($sub in @('课程教学','电子教材')) {
    $src = "${zyklocal}\${sub}"
    if (-not (Test-Path $src)) { Log "跳过 $sub（本地不存在）"; continue }
    Log "开始 scp $sub -> 生产"
    & scp -i $key -o StrictHostKeyChecking=no -r $src "${hostAddr}:${remoteBase}/" 2>&1
    Log "scp $sub 结束，退出码 $LASTEXITCODE"
}

# 5) 验证远程
Log "--- 远程验证 ---"
$rPptx = ssh -i $key -o StrictHostKeyChecking=no $hostAddr "find '$remoteBase/课程教学' -name '课件PPT-*.pptx' 2>/dev/null | wc -l"
Log "远程 PPTX 数：$($rPptx.Trim())"
$rVid = ssh -i $key -o StrictHostKeyChecking=no $hostAddr "find '$remoteBase/课程教学' -name '教学视频-*.pdf' 2>/dev/null | wc -l"
Log "远程 视频PDF 数：$($rVid.Trim())"
$rSize = ssh -i $key -o StrictHostKeyChecking=no $hostAddr "du -sh '$remoteBase/电子教材' 2>/dev/null; du -sh '$remoteBase/课程教学' 2>/dev/null"
Log "远程体积：$rSize"

Log "===== 部署完成 ====="
