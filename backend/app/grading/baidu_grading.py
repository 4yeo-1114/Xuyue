# -*- coding: utf-8 -*-
import base64
import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

OnBaiduResultCallback = Callable[[str, Optional[Tuple[str, list, dict]], Optional[Exception]], None]

import requests
from PIL import Image, ImageDraw

from app.grading.doc_convert import enhance_for_ocr

CREATE_TASK_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/correct_edu/create_task"
GET_RESULT_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/correct_edu/get_result"
TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"

# 百度侧已放量；提交/查询/并发拉到 30 封顶
_BAIDU_CREATE_QPS = max(1, int(os.environ.get("BAIDU_CREATE_QPS", os.environ.get("BAIDU_QPS_MAX", "30"))))
_BAIDU_GET_RESULT_QPS = max(1, int(os.environ.get("BAIDU_GET_RESULT_QPS", os.environ.get("BAIDU_QPS_MAX", "30"))))
_BAIDU_BACKEND_CONCURRENCY = max(1, int(os.environ.get("BAIDU_BACKEND_CONCURRENCY", "30")))
# 提交前长边限幅：超过该像素数则等比缩小，加速百度侧处理并避免超大图 base64 超限。
# 0 表示禁用。缩放后百度返回的像素坐标会按 scale 放大回原图坐标（见 _scale_baidu_coords）。
_BAIDU_UPLOAD_MAX_SIDE = int(os.environ.get("BAIDU_UPLOAD_MAX_SIDE", "2400"))
# task_id -> 提交时的等比缩放比例（>1 表示已缩小）；仅用于结果坐标还原
_task_scale_map: Dict[str, float] = {}


class _SlidingWindowRateLimiter:
    """全局滑动窗口：任意 1 秒内最多 max_per_second 次 acquire。"""

    def __init__(self, max_per_second: int):
        self._max = max(1, max_per_second)
        self._lock = threading.Lock()
        self._times: deque = deque()

    def acquire(self) -> None:
        while True:
            sleep_s = 0.0
            with self._lock:
                now = time.time()
                while self._times and now - self._times[0] >= 1.0:
                    self._times.popleft()
                if len(self._times) < self._max:
                    self._times.append(now)
                    return
                sleep_s = max(0.02, 1.0 - (now - self._times[0]))
            time.sleep(sleep_s)


_create_rate_limiter = _SlidingWindowRateLimiter(_BAIDU_CREATE_QPS)
_get_rate_limiter = _SlidingWindowRateLimiter(_BAIDU_GET_RESULT_QPS)
_rate_limiter = _create_rate_limiter

_token_lock = threading.Lock()
_db_token_load_lock = threading.Lock()
_token_refresh_lock = threading.Lock()
_token_cache: dict = {
    "access_token": None,
    "expires_at": 0.0,
    "last_db_token": None,
    "db_token_invalid": False,
    "last_env_token": None,
    "env_token_invalid": False,
}
_db_token_cache: dict = {
    "access_token": None,
    "api_key": None,
    "secret_key": None,
    "checked_at": 0.0,
}
_DB_TOKEN_TTL_SEC = max(2.0, float(os.environ.get("BAIDU_DB_TOKEN_TTL_SEC", "10")))


def _get_db_baidu_credentials() -> Tuple[str, str, str]:
    now = time.time()
    with _token_lock:
        checked_at = float(_db_token_cache.get("checked_at") or 0.0)
        if (now - checked_at) < _DB_TOKEN_TTL_SEC:
            return (
                str(_db_token_cache.get("access_token") or "").strip(),
                str(_db_token_cache.get("api_key") or "").strip(),
                str(_db_token_cache.get("secret_key") or "").strip(),
            )

    # 参照答案模式会同时提交标准答案和多张学生试卷。串行化首次数据库
    # 读取，避免其他线程在 token 尚未加载完成时误命中空缓存。
    with _db_token_load_lock:
        now = time.time()
        with _token_lock:
            checked_at = float(_db_token_cache.get("checked_at") or 0.0)
            if (now - checked_at) < _DB_TOKEN_TTL_SEC:
                return (
                    str(_db_token_cache.get("access_token") or "").strip(),
                    str(_db_token_cache.get("api_key") or "").strip(),
                    str(_db_token_cache.get("secret_key") or "").strip(),
                )

        db = None
        try:
            from app.database import SessionLocal
            from app.models.system_settings import SystemSettings

            db = SessionLocal()
            row = db.query(SystemSettings).first()
            tok = str(getattr(row, "baidu_access_token", "") or "").strip() if row else ""
            api_key = str(getattr(row, "baidu_api_key", "") or "").strip() if row else ""
            secret_key = str(getattr(row, "baidu_secret_key", "") or "").strip() if row else ""
        except Exception:
            tok = api_key = secret_key = ""
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

        with _token_lock:
            _db_token_cache["access_token"] = tok
            _db_token_cache["api_key"] = api_key
            _db_token_cache["secret_key"] = secret_key
            _db_token_cache["checked_at"] = time.time()
        return tok, api_key, secret_key


def _get_db_access_token() -> str:
    """Compatibility wrapper used by the existing grading modules and tests."""
    return _get_db_baidu_credentials()[0]


def invalidate_baidu_auth_cache() -> None:
    """Make database credential updates visible to all subsequent OCR calls."""
    with _token_lock:
        _db_token_cache.update(
            {"access_token": None, "api_key": None, "secret_key": None, "checked_at": 0.0}
        )
        _token_cache.update(
            {
                "access_token": None,
                "expires_at": 0.0,
                "last_db_token": None,
                "db_token_invalid": False,
            }
        )


def request_baidu_access_token(api_key: str, secret_key: str) -> Tuple[str, float]:
    """Exchange permanent Baidu credentials for a time-limited access token."""
    key = str(api_key or "").strip()
    secret = str(secret_key or "").strip()
    if not key or not secret:
        raise RuntimeError("百度 API Key 和 Secret Key 不能为空")
    try:
        resp = requests.get(
            TOKEN_URL,
            params={
                "grant_type": "client_credentials",
                "client_id": key,
                "client_secret": secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json() or {}
    except requests.RequestException as exc:
        raise RuntimeError(f"连接百度鉴权服务失败: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError("百度鉴权服务返回了无效 JSON") from exc

    token = str(data.get("access_token") or "").strip()
    if not token:
        detail = str(data.get("error_description") or data.get("error") or "未知错误").strip()
        raise RuntimeError(f"百度 API Key/Secret Key 校验失败: {detail}")
    return token, max(0.0, float(data.get("expires_in") or 0.0))


def _persist_db_access_token(token: str) -> None:
    db = None
    try:
        from app.database import SessionLocal
        from app.models.system_settings import SystemSettings

        db = SessionLocal()
        row = db.query(SystemSettings).first()
        if row is not None:
            row.baidu_access_token = token
            db.commit()
    except Exception:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
    with _token_lock:
        _db_token_cache["access_token"] = token
        _db_token_cache["checked_at"] = time.time()


def _url_access_token(url: str) -> str:
    try:
        return str((parse_qs(urlparse(url).query).get("access_token") or [""])[0]).strip()
    except Exception:
        return ""


def _get_access_token(force_refresh: bool = False, invalid_token: str = "") -> str:
    try:
        from app.config import settings
    except Exception:
        settings = None

    access_token_env = (
        str(getattr(settings, "BAIDU_ACCESS_TOKEN", "") or "").strip()
        if settings is not None
        else (os.environ.get("BAIDU_ACCESS_TOKEN") or "").strip()
    )
    env_api_key = (
        str(getattr(settings, "BAIDU_API_KEY", "") or "").strip()
        if settings is not None
        else (os.environ.get("BAIDU_API_KEY") or "").strip()
    )
    env_secret_key = (
        str(getattr(settings, "BAIDU_SECRET_KEY", "") or "").strip()
        if settings is not None
        else (os.environ.get("BAIDU_SECRET_KEY") or "").strip()
    )
    now = time.time()

    if force_refresh:
        with _token_lock:
            _db_token_cache["checked_at"] = 0.0
            _token_cache["access_token"] = None
            _token_cache["expires_at"] = 0.0

    db_token, db_api_key, db_secret_key = _get_db_baidu_credentials()
    api_key = db_api_key or env_api_key
    secret_key = db_secret_key or env_secret_key
    with _token_lock:
        if db_token != _token_cache.get("last_db_token"):
            _token_cache["last_db_token"] = db_token
            _token_cache["db_token_invalid"] = False

        if db_token and not _token_cache.get("db_token_invalid"):
            if force_refresh:
                if invalid_token and db_token != invalid_token:
                    _token_cache["access_token"] = db_token
                    _token_cache["expires_at"] = now + 3600
                    return db_token
                _token_cache["db_token_invalid"] = True
            else:
                _token_cache["access_token"] = db_token
                _token_cache["expires_at"] = now + 3600
                return db_token

    if not force_refresh:
        with _token_lock:
            cached = str(_token_cache.get("access_token") or "").strip()
            exp = float(_token_cache.get("expires_at") or 0.0)
            if cached and exp > now + 30:
                return cached

    if api_key and secret_key:
        with _token_refresh_lock:
            if force_refresh and invalid_token:
                current_db_token, _, _ = _get_db_baidu_credentials()
                if current_db_token and current_db_token != invalid_token:
                    with _token_lock:
                        _token_cache["access_token"] = current_db_token
                        _token_cache["expires_at"] = time.time() + 3600
                        _token_cache["db_token_invalid"] = False
                    return current_db_token
            token, expires_in = request_baidu_access_token(api_key, secret_key)
            _persist_db_access_token(token)
            with _token_lock:
                _token_cache["access_token"] = token
                _token_cache["expires_at"] = time.time() + expires_in
                _token_cache["last_db_token"] = token
                _token_cache["db_token_invalid"] = False
            return token

    with _token_lock:
        if access_token_env != _token_cache.get("last_env_token"):
            _token_cache["last_env_token"] = access_token_env
            _token_cache["env_token_invalid"] = False

        if access_token_env and not _token_cache.get("env_token_invalid"):
            if force_refresh:
                _token_cache["env_token_invalid"] = True
            else:
                _token_cache["access_token"] = access_token_env
                _token_cache["expires_at"] = now + 3600
                return access_token_env

    if db_token and _token_cache.get("db_token_invalid"):
        raise RuntimeError("数据库配置的百度 Access Token 无效或已过期，请在“系统设置”配置百度 API Key/Secret Key 以自动刷新")
    if access_token_env and _token_cache.get("env_token_invalid"):
        raise RuntimeError("环境变量 BAIDU_ACCESS_TOKEN 无效或已过期。")
    raise RuntimeError("百度鉴权未配置：请设置 BAIDU_API_KEY/BAIDU_SECRET_KEY（推荐）或 BAIDU_ACCESS_TOKEN。")


def _build_url(api_url: str) -> str:
    token = _get_access_token()
    if not token:
        raise RuntimeError("BAIDU_ACCESS_TOKEN 未配置")
    # M6（暂缓）：百度 OCR rest/2.0 接口只接受 query 参数的 access_token，
    # 官方未提供 header 认证，改 header 会直接破坏批改能力。
    # 缓解措施：确保本模块不打印/记录完整 URL，部署侧在访问日志中对该 token 做脱敏。
    return f"{api_url}?access_token={token}"


def _post_json(
    url: str,
    payload: dict,
    timeout: int = 30,
    limiter: Optional[_SlidingWindowRateLimiter] = None,
) -> dict:
    """调用百度接口：限流 + 遇 QPS 错误(18)自动退避重试。"""
    lim = limiter or _create_rate_limiter
    max_retries = 12
    last_data: dict = {}
    for attempt in range(max_retries):
        lim.acquire()
        u = url
        if "access_token=" in url:
            base = url.split("?")[0]
            u = _build_url(base)
        resp = requests.post(
            u,
            data=json.dumps(payload, ensure_ascii=False),
            headers={"content-type": "application/json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        last_data = data
        ec = data.get("error_code")
        if ec in (110, "110", 111, "111"):
            try:
                _get_access_token(force_refresh=True, invalid_token=_url_access_token(u))
            except Exception as e:
                raise RuntimeError(str(e))
            continue
        # 18: Open api qps request limit reached
        if ec in (18, "18"):
            wait = min(3.0, 0.3 * (2 ** min(attempt, 4)))
            time.sleep(wait)
            continue
        return data
    raise RuntimeError(f"百度接口持续限流(QPS)，请稍后重试：{last_data}")


def _prepare_submit_image_bytes(image_path: str) -> Tuple[bytes, float]:
    """读图并返回 (待提交字节, 等比缩放比例 scale)。

    - 长边超过 BAIDU_UPLOAD_MAX_SIDE 时等比缩小（scale>1），加速百度侧处理并避免超大图 base64 超限。
    - GRADING_OCR_ENHANCE=off 且无需缩放时保持原始字节（行为不变）；否则对（可能缩放后的）图像
      按 enhance_for_ocr 档位增强并转 JPEG。任何异常回退原始字节（scale=1）。
    """
    raw = Path(image_path).read_bytes()
    mode = os.environ.get("GRADING_OCR_ENHANCE", "auto").strip().lower()
    try:
        from io import BytesIO as _BytesIO
        with Image.open(image_path) as im:
            w, h = im.size
            long_side = max(w, h)
            do_resize = _BAIDU_UPLOAD_MAX_SIDE > 0 and long_side > _BAIDU_UPLOAD_MAX_SIDE
            scale = 1.0
            if do_resize:
                scale = long_side / float(_BAIDU_UPLOAD_MAX_SIDE)
                im = im.resize(
                    (max(1, int(round(w / scale))), max(1, int(round(h / scale)))),
                    Image.LANCZOS,
                )
            if mode != "off":
                im = enhance_for_ocr(im)  # 同尺寸增强，不改变尺寸
            elif not do_resize:
                return raw, 1.0  # 无增强且无缩放：保持原字节
        buf = _BytesIO()
        im.save(buf, format="JPEG", quality=95)
        return buf.getvalue(), scale
    except Exception:
        return raw, 1.0  # 处理失败回退原始字节


def submit_task(image_path: str, stop_event: Optional[threading.Event] = None) -> str:
    if stop_event and stop_event.is_set():
        raise RuntimeError("已停止批改")
    img_bytes, submit_scale = _prepare_submit_image_bytes(image_path)
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
    payload = {"image": img_base64, "only_split": False}
    # 百度侧增强/方向检测：默认开启，提升模糊/倒置扫描件的题目识别率（减少漏题）。
    # 可用环境变量显式关闭：GRADING_BAIDU_ENHANCE=off / GRADING_BAIDU_DETECT_DIRECTION=off
    # （off/0/false/no 均视为关闭）。
    if os.environ.get("GRADING_BAIDU_ENHANCE", "").strip().lower() not in ("0", "false", "no", "off"):
        payload["enhance"] = True
    if os.environ.get("GRADING_BAIDU_DETECT_DIRECTION", "").strip().lower() not in ("0", "false", "no", "off"):
        payload["detect_direction"] = True
    data = _post_json(
        _build_url(CREATE_TASK_URL),
        payload,
        limiter=_create_rate_limiter,
    )
    task_id = str((data.get("result") or {}).get("task_id", "")).strip()
    if not task_id:
        raise RuntimeError(f"提交百度任务失败：{data}")
    if submit_scale != 1.0:
        _task_scale_map[task_id] = submit_scale
    return task_id


def get_result(task_id: str) -> dict:
    data = _post_json(
        _build_url(GET_RESULT_URL),
        {"task_id": task_id},
        limiter=_get_rate_limiter,
    )
    scale = _task_scale_map.get(task_id)
    if scale and scale != 1.0:
        _scale_baidu_coords(data, scale)
    return data


def _scale_area(area: dict, scale: float) -> None:
    for k in ("left_x", "left_y", "right_x", "right_y"):
        v = area.get(k)
        if isinstance(v, (int, float)):
            area[k] = int(round(v * scale))


def _scale_baidu_coords(data: dict, scale: float) -> None:
    """提交前若做过等比缩放，把百度返回的像素坐标放大回原图坐标（就地修改）。"""
    try:
        container = data if isinstance(data, dict) and "imageResults" in data else (data or {}).get("result", {})
        for img in (container.get("imageResults") or []):
            for q in (img.get("result") or []):
                for area in (q.get("questionArea") or []):
                    _scale_area(area, scale)
                for s in (q.get("slot") or []):
                    ha = (s or {}).get("handwritingArea") or {}
                    _scale_area(ha, scale)
    except Exception:
        pass


def _is_result_pending(data: dict) -> bool:
    err_msg = str(data.get("error_msg", "")).strip().lower()
    err_code = data.get("error_code")
    return (err_code in (1, "1", 2, "2", 50, 60)) or ("pending" in err_msg) or ("running" in err_msg)


def _check_baidu_api_error(data: dict) -> None:
    if not isinstance(data, dict):
        raise RuntimeError("百度批改返回非 JSON 对象")
    ec = data.get("error_code")
    if ec in (None, 0, "0"):
        return
    if _is_result_pending(data):
        return
    msg = str(data.get("error_msg") or data).strip()
    raise RuntimeError(f"百度批改失败({ec}): {msg}")


def extract_baidu_image_direction(data: dict) -> int:
    """从百度智能批改结果里取图像朝向码（0=正 1=逆时针90 2=逆时针180 3=逆时针270；-1=未知/未返回）。

    百度在 detect_direction=true 时可能在顶层、result、或 imageResults[i] 返回 direction / img_direction。
    取不到可靠值时返回 -1，调用方据此决定是否自动摆正（宁可不动，也不误转已正的卷子）。
    """
    def _pick(v) -> int | None:
        try:
            iv = int(v)
        except (TypeError, ValueError):
            return None
        return iv if iv in (0, 1, 2, 3) else None

    if not isinstance(data, dict):
        return -1
    candidates: list = [data]
    result = data.get("result")
    if isinstance(result, dict):
        candidates.append(result)
        for img in (result.get("imageResults") or []):
            if isinstance(img, dict):
                candidates.append(img)
    for c in candidates:
        for key in ("direction", "img_direction", "image_direction"):
            v = c.get(key)
            if v is not None:
                d = _pick(v)
                if d is not None:
                    return d
    # 部分返回不带 result 包裹，imageResults 直接挂顶层
    for img in (data.get("imageResults") or []):
        if isinstance(img, dict):
            for key in ("direction", "img_direction"):
                d = _pick(img.get(key))
                if d is not None:
                    return d
    return -1


def wait_result(
    task_id: str,
    wait_seconds: float = None,
    retry_wait_seconds: float = None,
    max_wait_seconds: int = 600,
    stop_event: Optional[threading.Event] = None,
) -> dict:
    if wait_seconds is None:
        wait_seconds = float(os.environ.get("BAIDU_RESULT_INITIAL_WAIT", "2.0"))
    if retry_wait_seconds is None:
        retry_wait_seconds = float(os.environ.get("BAIDU_RESULT_POLL_INTERVAL", "0.2"))
    if stop_event and stop_event.is_set():
        raise RuntimeError("已停止批改")
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    start = time.time()
    last = {}
    while True:
        if stop_event and stop_event.is_set():
            raise RuntimeError("已停止批改")
        last = get_result(task_id)
        if not _is_result_pending(last):
            _check_baidu_api_error(last)
            return last
        if time.time() - start >= max_wait_seconds:
            return last
        time.sleep(max(0.5, retry_wait_seconds))
        if stop_event and stop_event.is_set():
            raise RuntimeError("已停止批改")


def _bbox_from_area(area: dict) -> List[int]:
    return [
        int(area.get("left_x", 0)),
        int(area.get("left_y", 0)),
        int(area.get("right_x", 0)),
        int(area.get("right_y", 0)),
    ]


def _state_text(code: int) -> str:
    return {0: "未批", 1: "正确", 2: "错误", 3: "未作答"}.get(code, "未知")


def _result_label(result, partial_ratio=None) -> str:
    """对/错/未作答 原样返回；半对 拼上比例（如 半对（0.6））。"""
    r = str(result or "")
    if r == "半对":
        if partial_ratio is None:
            return "半对"
        try:
            ratio = min(1.0, max(0.0, float(partial_ratio)))
            return f"半对（{ratio:g}）"
        except (TypeError, ValueError):
            return "半对"
    return r or "错"


def _summarize_result(result_json: dict, sorted_blocks: list) -> str:
    # 百度返回的结果可能包裹在 "result" 键内
    data_container = result_json if "stat_result" in result_json else result_json.get("result", {})
    stat = data_container.get("stat_result") or {}
    all_n = int(stat.get("all", 0) or 0)
    corrected = int(stat.get("corrected", 0) or 0)
    correcting = int(stat.get("correcting", 0) or 0)
    lines = [f"总题量：{all_n}；已批改：{corrected}；批改中：{correcting}"]
    
    # 使用排序后的 blocks_with_result 生成展示文本
    for blk in sorted_blocks:
        q_seq = blk.get("baidu_real_name", blk.get("index", "?"))
        s_seq = blk["sub_index"]
        res_text = _result_label(blk.get("result"), blk.get("partial_ratio"))
        reason = blk.get("comment", "")

        if blk.get("baidu_is_slot"):
            lines.append(f"第{q_seq}题-作答区{s_seq}：{res_text}；{reason}")
        else:
            lines.append(f"第{q_seq}题：{res_text}")
            
    return "\n".join(lines)


def _sort_blocks_by_reading_order(blocks: list) -> list:
    """
    将提取出的题目坐标按照人的阅读顺序（从上到下，从左到右，两栏试卷则先左栏后右栏）重新排序，并重新分配 index。
    """
    if not blocks:
        return blocks
        
    # 找出页面的中心线，用于区分左右栏
    min_x = min(b["bbox"][0] for b in blocks)
    max_x = max(b["bbox"][2] for b in blocks)
    center_x = (min_x + max_x) / 2.0
    
    def sort_key(b):
        bbox = b["bbox"]
        # x坐标的中心点
        cx = (bbox[0] + bbox[2]) / 2.0
        # 判断是在左栏还是右栏 (0 为左栏, 1 为右栏)
        col = 0 if cx < center_x else 1
        # 同一栏内，按 Y 坐标排序（设置一定的容差，防止同一行的字轻微上下浮动导致顺序错乱）
        y_tolerance = 50
        y_group = bbox[1] // y_tolerance
        return (col, y_group, bbox[0])
        
    sorted_blocks = sorted(blocks, key=sort_key)
    
    # 重新分配 index
    # 同一个原始 q_index 的作答区应该在新的排序中保持同一个新的 q_index
    old_to_new_index = {}
    current_new_index = 1
    
    for b in sorted_blocks:
        old_idx = b["baidu_original_index"]
        if old_idx not in old_to_new_index:
            old_to_new_index[old_idx] = current_new_index
            current_new_index += 1
            
    for b in sorted_blocks:
        b["index"] = old_to_new_index[b["baidu_original_index"]]
        
    return sorted_blocks


def _parse_baidu_grade_result(result_json: dict, task_id: str) -> Tuple[str, list, dict]:
    if isinstance(result_json, dict) and not result_json.get("task_id"):
        result_json["task_id"] = task_id
    blocks_with_result = []

    if "imageResults" in result_json:
        image_results = result_json.get("imageResults") or []
    else:
        image_results = result_json.get("result", {}).get("imageResults") or []

    for img in image_results:
        for q in (img.get("result") or []):
            q_areas = q.get("questionArea") or []
            q_bbox = _bbox_from_area(q_areas[0]) if q_areas else [0, 0, 0, 0]
            slots = q.get("slot") or []
            q_index = int(q.get("seqence", 0)) + 1
            q_real_name = q.get("realQuestionId") or f"{q_index}"
            q_cr = int(q.get("correctResult", 0) or 0)
            if slots and isinstance(slots, list):
                for s in slots:
                    area = (s or {}).get("handwritingArea") or {}
                    s_bbox = _bbox_from_area(area) if area else q_bbox
                    s_seq = int((s or {}).get("seqence", 1) or 1)
                    s_cr = int((s or {}).get("correctResult", q_cr) or q_cr)
                    reason = str((s or {}).get("reason", "") or "").strip()
                    blocks_with_result.append(
                        {
                            "baidu_original_index": q_index,
                            "baidu_real_name": q_real_name,
                            "index": q_index,
                            "sub_index": s_seq,
                            "is_question": True,
                            "result": "对" if s_cr == 1 else ("未作答" if s_cr == 3 else ("半对" if s_cr == 4 else "错")),
                            "comment": reason,
                            "bbox": s_bbox,
                            "baidu_correct_result": s_cr,
                            "baidu_question_bbox": q_bbox,
                            "baidu_is_slot": True,
                            # 百度笔迹检测框：非空=引擎确实看到手写。保留下来给
                            # ink_evidence 当仲裁证据——VL 说「无笔迹」时不许强降级
                            # （2026-10-22 汪小燕_1：VL 误报无笔迹把判「对」的两题
                            # 降成未作答，空心圆画到字上）。
                            "baidu_handwriting_bbox": _bbox_from_area(area) if area else None,
                        }
                    )
            else:
                blocks_with_result.append(
                    {
                        "baidu_original_index": q_index,
                        "baidu_real_name": q_real_name,
                        "index": q_index,
                        "sub_index": 1,
                        "is_question": True,
                        "result": "对" if q_cr == 1 else ("未作答" if q_cr == 3 else ("半对" if q_cr == 4 else "错")),
                        "comment": "",
                        "bbox": q_bbox,
                        "baidu_correct_result": q_cr,
                        "baidu_question_bbox": q_bbox,
                        "baidu_is_slot": False,
                        "baidu_handwriting_bbox": None,
                    }
                )

    blocks_with_result = _sort_blocks_by_reading_order(blocks_with_result)
    for b in blocks_with_result:
        b["baidu_real_name"] = str(b["index"])

    return _summarize_result(result_json, blocks_with_result), blocks_with_result, result_json


def _apply_post_parse_guards(parsed: Tuple[str, list, dict], image_path: Optional[str]) -> Tuple[str, list, dict]:
    """判后反向闸：「未作答」但作答区有手写笔迹 → 「待确认」（不画圈）。

    判分变了则摘要文本按新 blocks 重算，避免文本还写「未作答」。
    """
    if not image_path:
        return parsed
    try:
        from app.grading.form_guard import apply_unanswered_ink_guard

        _text, blocks, raw = parsed
        if apply_unanswered_ink_guard(image_path, blocks):
            return _summarize_result(raw, blocks), blocks, raw
    except Exception:
        return parsed
    return parsed


def _poll_pending_tasks(
    pending: Dict[str, Tuple[str, str]],
    results: Dict[str, Tuple[str, list, dict]],
    errors: Dict[str, Exception],
    stop_event: Optional[threading.Event] = None,
    on_result: Optional[OnBaiduResultCallback] = None,
    image_by_key: Optional[Dict[str, str]] = None,
) -> bool:
    """轮询 pending 中所有 task；pending: uid -> (结果键, task_id)。"""
    progressed = False
    for uid, (key, task_id) in list(pending.items()):
        if stop_event and stop_event.is_set():
            break
        try:
            data = get_result(task_id)
        except Exception as e:
            errors[key] = e
            pending.pop(uid, None)
            progressed = True
            if on_result:
                on_result(key, None, e)
            continue
        if _is_result_pending(data):
            continue
        try:
            _check_baidu_api_error(data)
            parsed = _parse_baidu_grade_result(data, task_id)
            parsed = _apply_post_parse_guards(parsed, (image_by_key or {}).get(key))
            results[key] = parsed
            if on_result:
                on_result(key, parsed, None)
        except Exception as e:
            errors[key] = e
            if on_result:
                on_result(key, None, e)
        pending.pop(uid, None)
        progressed = True
    return progressed


def baidu_grade_batch(
    items: List[Tuple[str, str]],
    stop_event: Optional[threading.Event] = None,
    on_result: Optional[OnBaiduResultCallback] = None,
) -> Tuple[Dict[str, Tuple[str, list, dict]], Dict[str, Exception]]:
    """
    批量异步批改：按 2QPS 连续提交，首批提交后等待 initial_wait，再满速 2QPS 轮询。
    items: [(结果键, 图片路径)]，结果键建议用试卷文件名。
    on_result: 每张卷百度侧完成后立即回调 (key, parsed_tuple|None, error|None)，用于流水线留痕。
    """
    keyed_items: List[Tuple[str, str]] = []
    for key, path in items:
        k = str(key or "").strip()
        p = str(path or "").strip()
        if k and p:
            keyed_items.append((k, p))

    results: Dict[str, Tuple[str, list, dict]] = {}
    errors: Dict[str, Exception] = {}
    # uid -> (结果键, task_id)；不用文件名作键，避免同名/规范化后撞键导致 task_id 被覆盖、永远漏批
    pending: Dict[str, Tuple[str, str]] = {}
    pending_seq = 0
    if not keyed_items:
        return results, errors

    result_keys = [k for k, _ in keyed_items]
    image_by_key = {k: p for k, p in keyed_items}
    if len(result_keys) != len(set(result_keys)):
        dupes = {k for k in result_keys if result_keys.count(k) > 1}
        print(f"警告：批量批改存在重复结果键 {dupes}，可能导致漏批，请检查文件名")

    initial_wait = float(os.environ.get("BAIDU_RESULT_INITIAL_WAIT", "2.0"))
    poll_idle_sleep = float(os.environ.get("BAIDU_RESULT_POLL_INTERVAL", "0.2"))
    max_wait = int(os.environ.get("BAIDU_RESULT_MAX_WAIT", "600"))
    pipeline_window = max(1, min(_BAIDU_BACKEND_CONCURRENCY, len(keyed_items)))

    first_submit_at: Optional[float] = None
    submit_idx = 0
    deadline = time.time() + max_wait

    def _notify_error(key: str, err: Exception) -> None:
        errors[key] = err
        if on_result:
            on_result(key, None, err)

    def _notify_all_pending(err: Exception) -> None:
        seen: set = set()
        for _, (key, _task_id) in list(pending.items()):
            if key in seen:
                continue
            seen.add(key)
            _notify_error(key, err)
        pending.clear()

    while submit_idx < len(keyed_items) or pending:
        if stop_event and stop_event.is_set():
            _notify_all_pending(RuntimeError("已停止批改"))
            break
        if time.time() >= deadline:
            _notify_all_pending(RuntimeError("百度批改超时"))
            while submit_idx < len(keyed_items):
                key, _path = keyed_items[submit_idx]
                submit_idx += 1
                if key not in errors and key not in results:
                    _notify_error(key, RuntimeError("百度批改超时（未提交或未返回）"))
            break

        while submit_idx < len(keyed_items):
            if stop_event and stop_event.is_set():
                break
            key, path = keyed_items[submit_idx]
            submit_idx += 1
            try:
                task_id = submit_task(path, stop_event=stop_event)
                pending_seq += 1
                pending[str(pending_seq)] = (key, task_id)
                if first_submit_at is None:
                    first_submit_at = time.time()
            except Exception as e:
                _notify_error(key, e)
                print(f"百度提交批改失败 [{key}]: {e}")

            # 先填满后台并发窗口（约 4 路），再开始与提交交错轮询
            if len(pending) >= pipeline_window or submit_idx >= len(keyed_items):
                break

        now = time.time()
        all_submitted = submit_idx >= len(keyed_items)
        ready_to_poll = first_submit_at is not None and (
            all_submitted or (now - first_submit_at) >= initial_wait
        )
        if pending and ready_to_poll:
            progressed = _poll_pending_tasks(
                pending, results, errors, stop_event=stop_event, on_result=on_result,
                image_by_key=image_by_key,
            )
            if pending and not progressed:
                time.sleep(max(0.1, poll_idle_sleep))
        elif submit_idx < len(keyed_items):
            time.sleep(0.02)
        elif pending:
            if first_submit_at is None:
                first_submit_at = now
            wait_left = initial_wait - (now - first_submit_at)
            if wait_left > 0:
                if stop_event:
                    if stop_event.wait(wait_left):
                        _notify_all_pending(RuntimeError("已停止批改"))
                        break
                else:
                    time.sleep(wait_left)
            else:
                progressed = _poll_pending_tasks(
                    pending, results, errors, stop_event=stop_event, on_result=on_result,
                    image_by_key=image_by_key,
                )
                if pending and not progressed:
                    time.sleep(max(0.1, poll_idle_sleep))

    return results, errors


def baidu_grade_single(image_path: str, stop_event: Optional[threading.Event] = None) -> Tuple[str, list, dict]:
    """
    返回:
    - result_text: 展示用文本
    - blocks_with_result: 兼容原留痕绘制的结构(按作答区 bbox 打勾/叉，避免漏批)
    - raw_result: 百度原始响应，供额外绘制作答区圈选
    """
    task_id = submit_task(image_path, stop_event=stop_event)
    result_json = wait_result(task_id, stop_event=stop_event)
    parsed = _parse_baidu_grade_result(result_json, task_id)
    return _apply_post_parse_guards(parsed, image_path)


# 智能模型批改（baidu）勾叉使用更轻的留痕尺寸，避免打印时过粗、遮挡作答区。
BAIDU_CHECK_CROSS_SCALE = 0.2


def _draw_manual_notes_on_image(draw, img_w: int, img_h: int, blocks_with_result: list) -> None:
    """在每道题作答区下方用红色写老师手动批注（卷面留痕）。

    仅绘制 blocks 里的 manual_note 字段；AI 自动评语（comment）仍只出现在结果文本框。
    """
    from app.grading.pipeline import _load_cjk_font

    note_font = None
    for blk in blocks_with_result:
        note = str(blk.get("manual_note") or "").strip()
        if not note:
            continue
        bbox = blk.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            x_min, y_min, x_max, y_max = (int(float(v)) for v in bbox[:4])
        except (TypeError, ValueError):
            continue
        if x_max <= x_min or y_max <= y_min:
            continue
        if note_font is None:
            note_font = _load_cjk_font(max(28, int(min(img_w, img_h) * 0.016)))
        if note_font is None:
            return
        # 按作答区宽度折算每行最大字符数（右侧留一点边距）
        try:
            char_w = max(12, draw.textlength("中", font=note_font))
        except Exception:
            char_w = note_font.size
        max_chars = max(6, int((img_w - x_min - 24) / char_w))
        lines: list = []
        for seg in note.split("\n"):
            seg = seg.rstrip()
            while len(seg) > max_chars:
                lines.append(seg[:max_chars])
                seg = seg[max_chars:]
            if seg:
                lines.append(seg)
        line_h = int(note_font.size * 1.4)
        ty = y_max + int(line_h * 0.4)
        for ln in lines:
            if ty + line_h > img_h:
                break
            draw.text((x_min, ty), ln, fill="#d62727", font=note_font, anchor="ls")
            ty += line_h


def draw_baidu_marks_and_save(
    image_path: str,
    blocks_with_result: list,
    baidu_raw: dict,
    result_dir: str,
    file_stem: str,
    *,
    check_cross_scale: float = BAIDU_CHECK_CROSS_SCALE,
    question_notes: Optional[dict] = None,
    paper_note: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    复用项目原留痕风格:
    - 题目坐标处打 √/×（未作答画空心圆 ○——2026-10-16 起没填答案也不能什么都不标）
    - 老师手动批注写到卷面留痕
    """
    from app.grading.pipeline import draw_real_marks_and_save, draw_marks_only_and_save, draw_manual_annotations

    orig_name, ann_name = draw_real_marks_and_save(
        image_path, blocks_with_result, result_dir, file_stem, check_cross_scale=check_cross_scale
    )
    marks_only = draw_marks_only_and_save(
        image_path, blocks_with_result, result_dir, file_stem, check_cross_scale=check_cross_scale
    )

    annotated_path = Path(result_dir) / ann_name
    marks_only_path = Path(result_dir) / marks_only

    for target in (annotated_path, marks_only_path):
        if not target.is_file():
            continue
        img = Image.open(str(target)).convert("RGB")
        draw = ImageDraw.Draw(img)
        img_w, img_h = img.size
        # 老师手动批注（每道题一句 + 整卷总评）写到卷面留痕上
        draw_manual_annotations(draw, img_w, img_h, blocks_with_result, question_notes, paper_note)
        img.save(str(target), quality=95)

    return orig_name, ann_name, marks_only
