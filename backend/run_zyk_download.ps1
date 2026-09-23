# 叙阅资料库课件下载（第二批 8 科，幂等续跑）。脱离会话执行，写日志。
$ErrorActionPreference = 'Continue'
Set-Location 'D:\叙阅\叙阅迁移包_20260920\backend'
& '.\venv\Scripts\python.exe' '.\scripts\smartedu_fetch_courseware.py' `
    --scope '小学:道德与法治:统编版,小学:科学:教科版,初中:物理:人教版,初中:化学:人教版,初中:生物学:人教版,初中:历史:统编版,初中:道德与法治:统编版,初中:地理:人教版' `
    --workers 12
