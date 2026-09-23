"""AI 输出红线词过滤器 — 拦截/改写 AI 助教生成内容中的伪科学话术。

词表来源：docs/plans/self-media-learning-methods-research-20260830.md §产品红线速记。
纯函数式：无 IO、无外部依赖、无网络，可单测。

用法（对接 LLM 流式输出）：
    filt = RedlineFilter()
    for token in llm_stream:
        fragment = filt.feed(token)
        if fragment:
            yield fragment
    tail = filt.flush()
    if tail:
        yield tail
"""

from typing import Dict, List, Optional, Tuple

# 短语 → 替换语（None = 删除，绝不出现）
REDLINE_PHRASES: Dict[str, Optional[str]] = {
    # 删除类：伪科学名目（无实证，伴智商税课程，绝不出现）
    "松果体激活": None,
    "照相记忆": None,
    "左右脑开发": None,
    "全脑开发": None,
    # 删除类：伪科学名目——感统失调（Ayres 感统对非自闭症证据弱）/右脑开发（Sperry 误读）/松果体玄学骗局别名
    "感统失调": None,
    "开天眼": None,
    "蒙眼识字": None,
    "右脑开发": None,
    # 替换类：话术换语言，保留行为内核
    "多巴胺戒断": "减少即时刺激",
    "21天养成习惯": "习惯养成需要时间",
    "21 天养成习惯": "习惯养成需要时间",
    "逆商AQ": "抗挫能力",
    "逆商 AQ": "抗挫能力",
    "莫扎特效应": "音乐欣赏",
    "脑波音乐": "音乐放松",
    "游戏上瘾": "过度游戏",
    "短视频上瘾": "过度刷短视频",
    "潜能翻倍": "能力提升",
    "决定一生": "影响深远",
    "窗口期": "关键阶段",
    # 替换类：快乐族话术——低/高级快乐换语言（键必须带「快乐」二字，避免误伤「低级错误」等正常表达）
    "低级的快乐靠多巴胺": "不同活动带来不同成长价值",
    "低级快乐": "即时快乐",
    "高级快乐": "长期成长",
    # 替换类：多巴胺/专注力/意志力话术——只拦具体组合，不加裸「多巴胺」「上瘾」「戒断」；专注力只替换勿删除
    "多巴胺成瘾": "过度依赖即时刺激",
    "专注力训练": "专注习惯培养",
    "意志力是肌肉": "循序渐进培养自控",
}


class RedlineFilter:
    """流式红线词过滤器。

    设计要点：
      - 最长短语优先匹配：先匹配长短语，避免短前缀误伤
      - 滑动窗口缓冲：当缓冲尾是某短语的前缀时保持不释放——
        LLM 会把中文短语拆到多个 token，逐 token 硬删会拆字出错
      - 删除类命中后合并相邻空白，不留双空格残渣；替换类直接替换
      - flush()：流结束时释放残留缓冲（残留不可能构成完整命中）
    """

    def __init__(self, phrases: Optional[Dict[str, Optional[str]]] = None) -> None:
        self._phrases: Dict[str, Optional[str]] = dict(REDLINE_PHRASES) if phrases is None else dict(phrases)
        # 最长短语优先（等长时保持 dict 顺序，无实际影响）
        self._sorted: List[str] = sorted(self._phrases.keys(), key=len, reverse=True)
        # 所有短语的所有前缀，用于判断缓冲尾是否需要保持
        self._prefixes = {
            phrase[:i]
            for phrase in self._phrases
            for i in range(1, len(phrase) + 1)
        }
        self._buf = ""
        # 删除类命中后的空白合并状态
        self._pending_merge = False
        self._merge_has_left_ws = False

    # ── 对外接口 ──────────────────────────────────────────────

    def feed(self, chunk: str) -> str:
        """输入 LLM 分片 token，返回此刻可安全释放的片段（可为空串）。"""
        self._buf += chunk
        out: List[str] = []
        while True:
            match = self._find_match(self._buf)
            if match is not None:
                start, end, phrase = match
                safe = self._buf[:start]
                stripped = safe.rstrip()
                held_ws = safe[len(stripped):]
                if stripped:
                    out.append(stripped)
                    self._pending_merge = False
                repl = self._phrases[phrase]
                if repl is not None:
                    # 替换类：保留删除/替换前已有的空白，直接替换短语
                    if held_ws:
                        out.append(held_ws)
                    out.append(repl)
                    self._pending_merge = False
                else:
                    # 删除类：丢掉前面的空白，等下一次释放时合并为单个空格
                    self._pending_merge = True
                    self._merge_has_left_ws = bool(held_ws)
                self._buf = self._buf[end:]
                continue
            # 无完整命中：释放除"可能是短语前缀"的尾部以外的内容
            hold = self._hold_len()
            if hold > 0:
                safe = self._buf[:-hold]
                self._buf = self._buf[-hold:]
            else:
                safe = self._buf
                self._buf = ""
            if safe:
                out.append(self._emit(safe))
            break
        return "".join(out)

    def flush(self) -> str:
        """流结束时释放残留缓冲。残留不可能构成完整命中，直接原样放行。"""
        tail = self._emit(self._buf)
        self._buf = ""
        self._pending_merge = False
        self._merge_has_left_ws = False
        return tail

    # ── 内部 ──────────────────────────────────────────────────

    def _find_match(self, text: str) -> Optional[Tuple[int, int, str]]:
        """返回 text 中最靠左的完整命中 (start, end, phrase)；无命中返回 None。

        同一位置多个短语命中时，长短语优先（_sorted 已按长度降序）。
        """
        n = len(text)
        for i in range(n):
            for phrase in self._sorted:
                p_len = len(phrase)
                if i + p_len <= n and text[i:i + p_len] == phrase:
                    return i, i + p_len, phrase
        return None

    def _hold_len(self) -> int:
        """缓冲尾需要保持不释放的长度（最长前缀优先）。

        除"能成为某短语前缀"的尾部外，还要把前缀前面的空白一起保持：
        这样短语在后续 feed 里被删除时，前面的空白仍在缓冲内，可被合并，
        避免"空白已释放、删除后才补合并"造成双空格残渣。
        """
        n = len(self._buf)
        hold = 0
        for i in range(n, 0, -1):
            if self._buf[-i:] in self._prefixes:
                hold = i
                break
        j = n - hold - 1
        while j >= 0 and self._buf[j].isspace():
            hold += 1
            j -= 1
        return hold

    def _emit(self, safe: str) -> str:
        """释放片段时应用删除后的空白合并：把删除点两侧空白并为单个空格。"""
        if self._pending_merge:
            self._pending_merge = False
            left = self._merge_has_left_ws
            self._merge_has_left_ws = False
            if left or (safe and safe[0].isspace()):
                return " " + safe.lstrip()
            return safe
        return safe


# ── 整段过滤（纯函数，供非流式整段 JSON 的 LLM 出口对接）────────────────

def filter_text(text: str) -> str:
    """整段文本红线过滤，语义与流式 RedlineFilter 等价。

    - 命中 None（删除类）：删除短语并合并相邻空白，不留双空格残渣
    - 命中 str（替换类）：替换为改写语
    - 最长短语优先匹配

    复用 RedlineFilter 滑窗逻辑：整段一次性 feed + flush 即与逐 token
    流式结果一致（流式把文本拆成块喂入，等价于整段喂入的退化情形）。
    """
    filt = RedlineFilter()
    return filt.feed(text) + filt.flush()


def filter_dict(data: dict, keys: List[str]) -> dict:
    """对 dict 中指定 key 的字符串值做红线过滤，返回新 dict。

    - 仅过滤 keys 白名单内的字符串值；值若是 dict 则递归进入（同样白名单）
    - 不存在的 key / 非字符串值（int/bool/None/list 等）原样保留
    - 不原地修改原对象，返回全新 dict
    """
    key_set = set(keys)
    out: Dict = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = filter_dict(v, keys)
        elif isinstance(v, str) and k in key_set:
            out[k] = filter_text(v)
        else:
            out[k] = v
    return out
