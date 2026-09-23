# 叙阅资料库部署进度监控：轮询远程已收字节 vs 本地总量，画 ASCII 进度条。
# 状态覆盖写到 zyk_progress.txt（单行最新）；本脚本脱离会话后台跑。
$key        = 'D:\叙阅\id_ed25519_gradebuddy'
$hostAddr   = 'root@120.26.101.0'
$remoteBase = '/www/wwwroot/教育项目/批改君/后端/grading_data_all/_shared/zyk_data'
$out        = 'D:\叙阅\叙阅迁移包_20260920\backend\zyk_progress.txt'
$total      = 14990184530   # 本地课程教学+电子教材总字节（部署启动时测）
$prev       = 0
$prevTime   = Get-Date
$speed      = 0

function Bar([double]$p) {
    $w = 40
    $f = [int][math]::Floor($p / 100 * $w)
    if ($f -gt $w) { $f = $w }
    $bar = '='
    for ($i = 1; $i -lt $w; $i++) {
        if ($i -lt $f) { $bar += '=' }
        elseif ($i -eq $f) { $bar += '>' }
        else { $bar += ' ' }
    }
    return $bar
}
function FmtDur([double]$s) {
    if ($s -lt 0) { return '...' }
    $s = [int]$s
    if ($s -ge 3600) { return ('{0}h{1}m' -f [int]($s / 3600), [int](($s % 3600) / 60)) }
    if ($s -ge 60)   { return ('{0}m{1:00}s' -f [int]($s / 60), ($s % 60)) }
    return ('{0}s' -f $s)
}

while ($true) {
    $r = ssh -i $key -o StrictHostKeyChecking=no $hostAddr "du -sb '$remoteBase/课程教学' '$remoteBase/电子教材' 2>/dev/null" 2>$null
    $done = 0
    $ok = $false
    foreach ($ln in $r) {
        if ($ln -match '^\s*(\d+)\s') { $done += [int64]$Matches[1]; $ok = $true }
    }
    $now = Get-Date
    $dt = ($now - $prevTime).TotalSeconds
    if ($ok -and $done -ge $prev -and $dt -ge 2) {
        $speed = ($done - $prev) / $dt
        $prev = $done
        $prevTime = $now
    }
    $pct = 0
    if ($total -gt 0) { $pct = [math]::Min(100.0, $done * 100.0 / $total) }
    $eta = -1
    if ($speed -gt 0) { $eta = ($total - $done) / $speed }
    $line = '{0} [{1}] {2,5:N1}%  {3,6:N2}/{4,5:N2} GB  {5,6:N1} MB/s  ETA {6}' -f `
        (Get-Date -Format 'HH:mm:ss'), (Bar $pct), $pct, ($done / 1GB), ($total / 1GB), ($speed / 1MB), (FmtDur $eta)
    Set-Content -Path $out -Value $line -Encoding ascii
    if ($done -ge $total) { break }
    Start-Sleep -Seconds 6
}
