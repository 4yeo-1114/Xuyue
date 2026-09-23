import { useEffect, useState } from "react";
import * as dd from "dingtalk-jsapi";
import { API_PREFIX } from "@/config/api";

const TOKEN_KEY = "grade_buddy_access_token";

export default function DingTalkEntry() {
  const [err, setErr] = useState("");

  useEffect(() => {
    // 不在钉钉里打开：给个明确提示，别白屏
    if (!dd.env.platform || dd.env.platform === "notInDingTalk") {
      setErr("请在钉钉工作台中打开「叙阅」");
      return;
    }

    // 工作台打开时，网址里会自动带上 corpId
    const corpId =
      new URLSearchParams(location.search).get("corpId") ||
      (import.meta.env.VITE_DINGTALK_CORP_ID as string) ||
      "";

    dd.ready(async () => {
      try {
        // 1) 跟钉钉要「进门条」
        const res: any = await dd.runtime.permission.requestAuthCode({ corpId });
        const code = res?.code;

        // 2) 拿进门条找叙阅后端换令牌
        const r = await fetch(`${API_PREFIX}/auth/dingtalk-login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data?.detail || "免登失败");

        // 3) 存下令牌，跳到目标页（带 redirect 时落到指定页，否则回主页）
        localStorage.setItem(TOKEN_KEY, data.data.access_token);
        const redirect = new URLSearchParams(window.location.search).get("redirect") || "";
        // 只允许站内同源相对路径：以单个 / 开头、且不是 //（防协议相对外跳）
        const safeRedirect = /^\/(?!\/)/.test(redirect) ? redirect : "/";
        location.replace(safeRedirect);
      } catch (e: any) {
        setErr(e?.message || String(e));
      }
    });
  }, []);

  if (err) {
    return (
      <div style={{ padding: 40, fontSize: 16, textAlign: "center" }}>
        <p>❌ {err}</p>
        <p style={{ color: "#888", fontSize: 14 }}>（把这句话截图发给技术，能快速定位）</p>
      </div>
    );
  }
  return <div style={{ padding: 40, textAlign: "center" }}>正在登录…</div>;
}
