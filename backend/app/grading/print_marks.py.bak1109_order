# -*- coding: utf-8 -*-
"""
批改留痕打印：调用系统打印机打印「仅留痕」图片（与 批改作业_fastAPI/批改功能/print_marks.py 逻辑一致）。
仅在 Windows 且已安装 pywin32 时可用；其他环境返回明确错误。
"""
from __future__ import annotations

import os
import re
from typing import Optional, Tuple

try:
    import win32print
    import win32ui
    import win32con
    from PIL import Image
    from PIL import ImageOps
    from PIL import ImageWin
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False

# 打印机状态码与中文描述
_PRINTER_STATUS_MAP = {
    0: "就绪",
    0x00000001: "暂停",
    0x00000002: "错误",
    0x00000004: "正在删除",
    0x00000008: "脱机",
    0x00000010: "缺纸",
    0x00000020: "正在打印",
    0x00000040: "初始化",
    0x00000080: "正在清理",
    0x00000100: "无墨粉",
    0x00000200: "无墨盒",
    0x00000400: "正在校准",
    0x00000800: "正在处理",
    0x00001000: "正在打开",
    0x00002000: "墨盒耗尽",
    0x00004000: "墨粉不足",
    0x00008000: "墨粉耗尽",
}


def list_printers_with_status():
    """
    列出本机打印机及状态。仅 Windows 可用。
    :return: (success: bool, result)
      成功时 result 为 list[dict]，每项 { "name", "is_default", "status", "status_text", "ready" }
      ready 为 True 表示工作正常（状态为就绪）。
      失败时 result 为错误信息 str。
    """
    if not _WIN32_AVAILABLE:
        return False, "仅支持 Windows，请安装 pywin32"
    try:
        default_name = win32print.GetDefaultPrinter()
    except Exception:
        default_name = None
    try:
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
    except Exception as e:
        return False, str(e)
    result = []
    for item in printers:
        name = item[2]
        is_default = name == default_name
        status = 0
        status_text = "就绪"
        bins = []
        try:
            h = win32print.OpenPrinter(name)
            try:
                info = win32print.GetPrinter(h, 2)
                status = info.get("Status", 0)
                status_text = _PRINTER_STATUS_MAP.get(status, f"未知({status})")
            finally:
                win32print.ClosePrinter(h)
        except Exception:
            status_text = "无法获取状态"
        try:
            bins = list_printer_bins(name)
        except Exception:
            bins = []
        result.append({
            "name": name,
            "is_default": is_default,
            "status": status,
            "status_text": status_text,
            "ready": status == 0,
            "bins": bins,
        })
    return True, result


def list_printer_bins(printer_name: str) -> list[dict]:
    if not _WIN32_AVAILABLE:
        return []
    try:
        cap_bins = int(getattr(win32con, "DC_BINS", 6))
        cap_binnames = int(getattr(win32con, "DC_BINNAMES", 12))
        h = win32print.OpenPrinter(printer_name)
        try:
            info = win32print.GetPrinter(h, 2)
            port = info.get("pPortName") or info.get("PortName") or None
            dm = info.get("pDevMode")
        finally:
            win32print.ClosePrinter(h)
        try:
            bin_ids = win32print.DeviceCapabilities(printer_name, port, cap_bins, None, dm) or []
            bin_names = win32print.DeviceCapabilities(printer_name, port, cap_binnames, None, dm) or []
        except Exception:
            bin_ids = win32print.DeviceCapabilities(printer_name, port, cap_bins) or []
            bin_names = win32print.DeviceCapabilities(printer_name, port, cap_binnames) or []
        ids = list(bin_ids) if isinstance(bin_ids, (list, tuple)) else []
        names = list(bin_names) if isinstance(bin_names, (list, tuple)) else []
        out = []
        for i in range(min(len(ids), len(names))):
            bid = ids[i]
            nm = names[i]
            try:
                bid_int = int(bid)
            except Exception:
                continue
            if isinstance(nm, bytes):
                try:
                    nm = nm.decode("gbk", errors="ignore")
                except Exception:
                    nm = nm.decode(errors="ignore")
            nm = str(nm).replace("\x00", "").strip()
            if not nm:
                nm = f"纸盒{bid_int}"
            out.append({"id": bid_int, "name": nm})
        return out
    except Exception:
        return []


def print_image(
    image_path: str,
    printer_name: str = None,
    copies: int = 1,
    paper_size: str = "a4",
    custom_paper_mm: Optional[Tuple[float, float]] = None,
    paper_source: Optional[int] = None,
) -> tuple:
    """
    使用系统默认打印机打印图片（与试卷同尺寸的留痕图，用于叠在试卷上）。

    :param image_path: 留痕图片的本地绝对路径
    :param printer_name: 打印机名称，None 表示默认打印机
    :param copies: 打印份数
    :param paper_size: 纸张预设（default 表示不修改驱动的纸张设置）
    :return: (success: bool, message: str)
    """
    if not _WIN32_AVAILABLE:
        return False, "打印功能仅支持 Windows 系统，请安装 pywin32 并在本机执行打印。"

    if not image_path or not os.path.isfile(image_path):
        return False, "图片文件不存在"

    return print_images(
        [image_path],
        printer_name=printer_name,
        copies=copies,
        duplex=False,
        paper_size=paper_size,
        custom_paper_mm=custom_paper_mm,
        paper_source=paper_source,
    )


# Windows DMPAPER_*（见 wingdi.h），用于 SetPrinter DEVMODE
_PAPER_DMPAPER = {
    "a3": 8,  # DMPAPER_A3
    "a4": 9,  # DMPAPER_A4
    "a5": 11,  # DMPAPER_A5
    "b4": 34,  # DMPAPER_B4 JIS
    "b5": 35,  # DMPAPER_B5 JIS
    "letter": 1,  # DMPAPER_LETTER
    "legal": 5,  # DMPAPER_LEGAL
    "tabloid": 3,  # DMPAPER_TABLOID 11x17
}

_PAPER_MM = {
    "a3": (297.0, 420.0),
    "a4": (210.0, 297.0),
    "a5": (148.0, 210.0),
    "b4": (257.0, 364.0),
    "b5": (182.0, 257.0),
    "letter": (216.0, 279.0),
    "legal": (216.0, 356.0),
    "tabloid": (279.0, 432.0),
}

_DMPAPER_USER = 256


def _apply_print_devmode(
    printer_name: str,
    duplex: bool,
    paper_key: str,
    custom_paper_mm: Optional[Tuple[float, float]] = None,
    paper_source: Optional[int] = None,
):
    if not _WIN32_AVAILABLE:
        return None
    try:
        h = win32print.OpenPrinter(printer_name, {"DesiredAccess": win32print.PRINTER_ALL_ACCESS})
        try:
            info = win32print.GetPrinter(h, 2)
            dm = info.get("pDevMode")
            if dm is None:
                return None
            fields = int(getattr(dm, "Fields", 0))
            dm_duplex = int(getattr(win32con, "DM_DUPLEX", 0x1000))
            dm_papersize = int(getattr(win32con, "DM_PAPERSIZE", 0x0002))
            dm_paperlength = int(getattr(win32con, "DM_PAPERLENGTH", 0x0004))
            dm_paperwidth = int(getattr(win32con, "DM_PAPERWIDTH", 0x0008))
            dm_defaultsource = int(getattr(win32con, "DM_DEFAULTSOURCE", 0x0200))
            dm_orient = int(getattr(win32con, "DM_ORIENTATION", 0x0001))
            orient_portrait = int(getattr(win32con, "DMORIENT_PORTRAIT", 1))
            orient_landscape = int(getattr(win32con, "DMORIENT_LANDSCAPE", 2))

            fields |= dm_duplex
            dm.Duplex = 2 if duplex else 1  # 2: 长边双面, 1: 单面
            try:
                fields |= dm_defaultsource
                if isinstance(paper_source, int) and paper_source > 0:
                    dm.DefaultSource = int(paper_source)
            except Exception:
                pass

            pk = (paper_key or "a4").strip().lower()
            is_custom = pk == "custom" and custom_paper_mm is not None
            set_paper = pk != "default" and (pk in _PAPER_DMPAPER or is_custom)
            if set_paper:
                fields |= dm_papersize
                if is_custom:
                    w_mm, h_mm = custom_paper_mm
                    dm.PaperSize = _DMPAPER_USER
                    dm.PaperWidth = max(1, int(round(w_mm * 10.0)))
                    dm.PaperLength = max(1, int(round(h_mm * 10.0)))
                    fields |= dm_paperwidth | dm_paperlength
                else:
                    dm.PaperSize = _PAPER_DMPAPER[pk]

            if pk == "a3":
                fields |= dm_orient
                dm.Orientation = orient_landscape
            elif pk == "a4":
                fields |= dm_orient
                dm.Orientation = orient_portrait
            elif is_custom:
                try:
                    w_mm, h_mm = custom_paper_mm
                    fields |= dm_orient
                    dm.Orientation = orient_landscape if float(w_mm) > float(h_mm) else orient_portrait
                except Exception:
                    pass

            dm.Fields = fields
            info["pDevMode"] = dm
            win32print.SetPrinter(h, 2, info, 0)
            return dm
        finally:
            win32print.ClosePrinter(h)
    except Exception:
        pass
    return None


def _safe_device_cap(printer_dc, cap_id: int) -> int:
    """GetDeviceCaps 可能返回 0/-1；用于物理尺寸等。"""
    try:
        v = int(printer_dc.GetDeviceCaps(cap_id))
        return v if v > 0 else 0
    except Exception:
        return 0


def _dpi_from_image(image) -> Optional[Tuple[float, float]]:
    """Pillow 打开后的 dpi（JPEG/PNG 等）；无则返回 None，打印侧退回像素比例缩放。"""
    d = image.info.get("dpi")
    if isinstance(d, tuple) and len(d) >= 2:
        x, y = float(d[0]), float(d[1])
        if x > 0 and y > 0:
            return (x, y)
    return None


def _landscape_from_paper(
    paper_key: str,
    custom_paper_mm: Optional[Tuple[float, float]] = None,
) -> Optional[bool]:
    """由纸张预设推断页面是否横向；无法推断时返回 None。"""
    pk = (paper_key or "a4").strip().lower()
    if pk == "a3" or pk == "b4" or pk == "tabloid":
        return True
    if pk in ("a4", "a5", "b5", "letter", "legal"):
        return False
    if pk == "custom" and custom_paper_mm is not None:
        w_mm, h_mm = custom_paper_mm
        return float(w_mm) > float(h_mm)
    return None


def _page_landscape_from_caps(
    physical_width: int,
    physical_height: int,
    printable_width: int,
    printable_height: int,
) -> bool:
    if physical_width > 0 and physical_height > 0:
        return physical_width > physical_height
    return printable_width > printable_height


def _normalize_caps_to_landscape(
    physical_width: int,
    physical_height: int,
    printable_width: int,
    printable_height: int,
    page_landscape: bool,
) -> tuple[int, int, int, int]:
    """双面背面时驱动可能交换宽高；按锁定方向归一化，避免误判旋转 90°。"""
    cur_landscape = _page_landscape_from_caps(
        physical_width, physical_height, printable_width, printable_height
    )
    if cur_landscape == page_landscape:
        return physical_width, physical_height, printable_width, printable_height
    if physical_width > 0 and physical_height > 0:
        physical_width, physical_height = physical_height, physical_width
    if printable_width > 0 and printable_height > 0:
        printable_width, printable_height = printable_height, printable_width
    return physical_width, physical_height, printable_width, printable_height


def _compute_scaled_print_size(
    image,
    printer_dc,
    physical_width: int,
    physical_height: int,
) -> tuple[int, int]:
    """
    叠印：尽量按「扫描物理尺寸 → 打印机设备像素」映射后再整体缩放到整张物理纸内。
    有 DPI 时用 像素×(LOGPIXEL/DPI)；无 DPI 时退回 min(PHYSICAL/像素) 与旧版一致。
    """
    px_w, px_h = image.size
    dpi = _dpi_from_image(image)
    pw, ph = max(1, physical_width), max(1, physical_height)
    if dpi:
        dpi_x, dpi_y = dpi
        log_x = max(1, _safe_device_cap(printer_dc, win32con.LOGPIXELSX))
        log_y = max(1, _safe_device_cap(printer_dc, win32con.LOGPIXELSY))
        tw = px_w * (log_x / dpi_x)
        th = px_h * (log_y / dpi_y)
        s = min(pw / tw, ph / th)
        print_w = int(round(tw * s))
        print_h = int(round(th * s))
    else:
        s = min(pw / px_w, ph / px_h)
        print_w = int(round(px_w * s))
        print_h = int(round(px_h * s))
    return max(1, print_w), max(1, print_h)


def _norm_path(path: str) -> str:
    try:
        return os.path.normpath(os.path.abspath(str(path or "")))
    except Exception:
        return str(path or "")


def _should_swap_essay_duplex_sides(paths: list[str]) -> bool:
    """
    纸盒原稿 P1 朝上时，GDI 长边双面常把「先提交的一页」印在与朝上侧相反的一面，
    导致朝上侧出现 P2 留痕。作文留痕默认互换提交顺序 [P1,P2]→[P2,P1] 以对齐物理纸面。
    设 GRADING_DUPLEX_ESSAY_SWAP_SIDES=0 可关闭。
    """
    if len(paths) != 2:
        return False
    if not all(_is_essay_marks_file(p) for p in paths):
        return False
    return os.environ.get("GRADING_DUPLEX_ESSAY_SWAP_SIDES", "1").strip() != "0"


def _duplex_job_paths(image_paths) -> list:
    """
    双面同一任务：先按页码整理为 P1、P2…；作文留痕再按纸盒 P1 朝上习惯互换 sides。
    """
    paths = list(image_paths)
    if len(paths) <= 1:
        return paths
    paths = sorted(paths, key=lambda p: (_page_no_from_marks_filename(p), _norm_path(p)))
    if _should_swap_essay_duplex_sides(paths):
        paths = [paths[1], paths[0]]
    return paths


def _page_no_from_marks_filename(path: str) -> int:
    """从留痕文件名解析页码：无 _数字 后缀为第 1 页，_2 为第 2 页（背面）。"""
    stem = os.path.splitext(os.path.basename(str(path or "")))[0]
    if stem.startswith("marks_only_"):
        stem = stem[len("marks_only_") :]
    m = re.search(r"_(\d+)$", stem)
    if m:
        try:
            return max(1, int(m.group(1)))
        except ValueError:
            pass
    return 1


def _student_base_from_marks_filename(path: str) -> str:
    """同一学生多页留痕的分组键（去掉 marks_only_ 前缀与末尾页码）。"""
    stem = os.path.splitext(os.path.basename(str(path or "")))[0]
    if stem.startswith("marks_only_"):
        stem = stem[len("marks_only_") :]
    return re.sub(r"_\d+$", "", stem)


def sort_marks_filenames_for_print(filenames: list[str]) -> list[str]:
    """
    批量打印前按「学生块 + 页码」排序，保证双面时 P1 正面、P2 背面。
    不改变不同学生之间的相对顺序，仅纠正同一学生块内页码顺序。
    """
    if not filenames:
        return []
    blocks: list[tuple[str, list[str]]] = []
    current_base: Optional[str] = None
    current_block: list[str] = []
    for fn in filenames:
        base = _student_base_from_marks_filename(fn)
        if current_base is None or base == current_base:
            current_base = base
            current_block.append(fn)
        else:
            blocks.append((current_base, current_block))
            current_base = base
            current_block = [fn]
    if current_block:
        blocks.append((current_base or "", current_block))
    out: list[str] = []
    for _, block in blocks:
        block_sorted = sorted(
            block,
            key=lambda fn: (_page_no_from_marks_filename(fn), fn),
        )
        out.extend(block_sorted)
    return out


def _is_essay_marks_file(path: str) -> bool:
    """作文留痕按原扫描方向保存，双面打印时默认不额外旋转背面。"""
    bn = os.path.basename(str(path or "")).lower()
    return bn.startswith("marks_only_essay_")


def _duplex_back_orig_index(original_paths: list[str]) -> int:
    """双面 2 页时，传入顺序固定为：第 1 张正面，第 2 张背面。"""
    if len(original_paths) != 2:
        return -1
    return 1


def _apply_duplex_back_rotation(image, path: str, *, orig_idx: int, duplex_back_idx: int) -> object:
    """
    长边双面：打印机印背面时常整体翻转 180°（旁批从右变左且文字倒置）。
    普通留痕对背面图预旋转 180° 抵消；作文纸正反面叠印更依赖原扫描方向，
    默认不旋转作文背面，避免正面准确时背面被额外翻转。
    """
    if duplex_back_idx < 0 or orig_idx != duplex_back_idx:
        return image
    if _is_essay_marks_file(path) and os.environ.get("GRADING_DUPLEX_ROTATE_ESSAY_BACK", "0").strip() != "1":
        return image
    return image.transpose(Image.ROTATE_180)


def print_images(
    image_paths,
    printer_name: str = None,
    copies: int = 1,
    duplex: bool = False,
    paper_size: str = "a4",
    custom_paper_mm: Optional[Tuple[float, float]] = None,
    paper_source: Optional[int] = None,
) -> tuple:
    """
    一次打印多页（同一个打印任务）。
    duplex=True 时，同一任务内按「正面、背面」输出（例如 1页正面、2页背面）。
    """
    if not _WIN32_AVAILABLE:
        return False, "打印功能仅支持 Windows 系统，请安装 pywin32 并在本机执行打印。"
    if not image_paths:
        return False, "没有可打印的图片"
    try:
        if printer_name is None:
            printer_name = win32print.GetDefaultPrinter()
        original_paths = [_norm_path(p) for p in image_paths]
        job_paths = _duplex_job_paths(original_paths) if duplex else list(original_paths)
        duplex_pair = duplex and len(original_paths) == 2
        duplex_back_idx = _duplex_back_orig_index(original_paths) if duplex_pair else -1
        path_to_orig_idx = {_norm_path(p): i for i, p in enumerate(original_paths)}
        for p in job_paths:
            if not p or not os.path.isfile(p):
                return False, f"图片文件不存在: {p}"

        page_items: list[tuple[str, object, int]] = []
        for p in job_paths:
            im = Image.open(p, mode="r")
            im = ImageOps.exif_transpose(im)
            page_items.append((p, im.convert("RGB"), path_to_orig_idx.get(_norm_path(p), -1)))

        # 双面同一学生框：以正面（用户顺序第 1 张）的横竖向统一两页 90° 校正，避免正反面各自判断导致背面相对正面倒 180°
        duplex_ref_landscape: Optional[bool] = None
        if duplex_pair:
            for _, image, orig_idx in page_items:
                if orig_idx == 0:
                    duplex_ref_landscape = image.size[0] > image.size[1]
                    break

        original_dm = None
        try:
            hp = win32print.OpenPrinter(printer_name, {"DesiredAccess": win32print.PRINTER_ALL_ACCESS})
            try:
                info0 = win32print.GetPrinter(hp, 2)
                original_dm = info0.get("pDevMode")
            finally:
                win32print.ClosePrinter(hp)
        except Exception:
            original_dm = None

        dm_for_job = _apply_print_devmode(
            printer_name,
            duplex,
            paper_size or "a4",
            custom_paper_mm=custom_paper_mm,
            paper_source=paper_source,
        )

        try:
            for _ in range(max(1, int(copies))):
                printer_dc = win32ui.CreateDC()
                try:
                    printer_dc.CreatePrinterDC(printer_name)
                except Exception as e:
                    raise RuntimeError(
                        f"无法创建打印机设备上下文（CreateDC failed）。打印机「{printer_name}」"
                        "可能使用的是 IPP/WSD 类驱动（如 Microsoft IPP Class Driver），"
                        "与当前 GDI 打印方式不兼容。请在打印设置中改用其它打印机"
                        "（如 Microsoft Print to PDF）验证流程，或为该打印机安装官方 GDI 驱动"
                        f"（PCL/PostScript）。原始错误：{e}"
                    )
                printer_dc.SetMapMode(1)  # MM_TEXT
                if dm_for_job is not None:
                    try:
                        printer_dc.ResetDC(dm_for_job)
                    except Exception:
                        pass
                doc_name = os.path.basename(job_paths[0]) or "marks-batch"
                printer_dc.StartDoc(doc_name)
                duplex_page_landscape: Optional[bool] = (
                    _landscape_from_paper(paper_size or "a4", custom_paper_mm) if duplex else None
                )
                for page_idx, (path, image, orig_idx) in enumerate(page_items):
                    work = image.copy()
                    # 必须在 StartPage 之后再取设备能力：多数打印机驱动在 StartPage 前
                    # PHYSICAL* / OFFSET 等会不准或为 0，导致缩放与叠印位置错误。
                    printer_dc.StartPage()
                    physical_width = _safe_device_cap(printer_dc, win32con.PHYSICALWIDTH)
                    physical_height = _safe_device_cap(printer_dc, win32con.PHYSICALHEIGHT)
                    offset_x = int(printer_dc.GetDeviceCaps(win32con.PHYSICALOFFSETX))
                    offset_y = int(printer_dc.GetDeviceCaps(win32con.PHYSICALOFFSETY))
                    printable_width = _safe_device_cap(printer_dc, win32con.HORZRES)
                    printable_height = _safe_device_cap(printer_dc, win32con.VERTRES)
                    printable_width = max(1, printable_width)
                    printable_height = max(1, printable_height)

                    try:
                        if duplex:
                            if duplex_page_landscape is None:
                                duplex_page_landscape = _page_landscape_from_caps(
                                    physical_width,
                                    physical_height,
                                    printable_width,
                                    printable_height,
                                )
                            page_landscape = duplex_page_landscape
                            physical_width, physical_height, printable_width, printable_height = (
                                _normalize_caps_to_landscape(
                                    physical_width,
                                    physical_height,
                                    printable_width,
                                    printable_height,
                                    page_landscape,
                                )
                            )
                        else:
                            page_landscape = _page_landscape_from_caps(
                                physical_width,
                                physical_height,
                                printable_width,
                                printable_height,
                            )
                        if duplex_pair and duplex_ref_landscape is not None:
                            img_landscape = duplex_ref_landscape
                        else:
                            img_landscape = work.size[0] > work.size[1]
                        if img_landscape != page_landscape:
                            work = work.transpose(Image.ROTATE_90)
                    except Exception:
                        pass

                    work = _apply_duplex_back_rotation(
                        work,
                        path,
                        orig_idx=orig_idx,
                        duplex_back_idx=duplex_back_idx if duplex_pair else -1,
                    )

                    if physical_width > 0 and physical_height > 0:
                        print_width, print_height = _compute_scaled_print_size(
                            work, printer_dc, physical_width, physical_height
                        )
                        page_x = int(round((physical_width - print_width) / 2.0))
                        page_y = int(round((physical_height - print_height) / 2.0))
                        start_x = page_x - offset_x
                        start_y = page_y - offset_y
                    else:
                        # 驱动未提供物理纸尺寸时，仅在可打印区内等比居中（与旧行为接近）
                        img_width, img_height = work.size
                        ratio = min(printable_width / img_width, printable_height / img_height)
                        print_width = max(1, int(round(img_width * ratio)))
                        print_height = max(1, int(round(img_height * ratio)))
                        start_x = int(round((printable_width - print_width) / 2.0))
                        start_y = int(round((printable_height - print_height) / 2.0))

                    dib = ImageWin.Dib(work)
                    hdc = printer_dc.GetHandleOutput()
                    try:
                        hdc_int = int(hdc)
                    except (TypeError, ValueError):
                        hdc_int = hdc
                    dib.draw(hdc_int, (start_x, start_y, start_x + print_width, start_y + print_height))
                    try:
                        work.close()
                    except Exception:
                        pass
                    printer_dc.EndPage()
                printer_dc.EndDoc()
                printer_dc.DeleteDC()
        finally:
            if original_dm is not None:
                try:
                    hp2 = win32print.OpenPrinter(
                        printer_name, {"DesiredAccess": win32print.PRINTER_ALL_ACCESS}
                    )
                    try:
                        info2 = win32print.GetPrinter(hp2, 2)
                        info2["pDevMode"] = original_dm
                        win32print.SetPrinter(hp2, 2, info2, 0)
                    finally:
                        win32print.ClosePrinter(hp2)
                except Exception:
                    pass
            for _, im, _ in page_items:
                try:
                    im.close()
                except Exception:
                    pass
        return True, f"已发送至打印机: {printer_name}"
    except Exception as e:
        return False, f"打印失败: {str(e)}"


def images_to_pdf_bytes(image_paths, resolution: float = 150.0) -> bytes:
    """
    把多张留痕图按顺序合成一个 PDF（每图一页），用于「输出 PDF」替代物理打印。
    留痕图为白底红字（RGB），直接按图片尺寸/DPI 作为页尺寸，与叠印打印效果一致。
    纯 Pillow 实现，不依赖 pywin32 / 系统打印机，任何环境（含局域网访问）均可用。
    """
    import io

    from PIL import Image
    from PIL import ImageOps

    if not image_paths:
        raise ValueError("没有可导出的留痕图片")
    images = []
    try:
        for p in image_paths:
            if not p or not os.path.isfile(p):
                raise FileNotFoundError(f"图片文件不存在: {p}")
            im = Image.open(p, mode="r")
            im = ImageOps.exif_transpose(im)
            images.append(im.convert("RGB"))
        buf = io.BytesIO()
        images[0].save(
            buf,
            format="PDF",
            save_all=True,
            append_images=images[1:],
            resolution=resolution,
        )
        return buf.getvalue()
    finally:
        for im in images:
            try:
                im.close()
            except Exception:
                pass
