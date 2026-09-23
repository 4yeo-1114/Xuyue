import { toast } from "sonner";
import { translate, normalizeLocale } from "@/i18n";
import type { AppLocale } from "@/i18n/types";
import { localeStorageKey } from "@/services/localeApi";

const LOCALE_KEY_PREFIX = "grade_buddy_locale_";

/** 组件外无法用 useLocale，直接读取 localStorage 缓存的界面语言 */
function currentLocale(): AppLocale {
  try {
    const keys: string[] = [localeStorageKey(null)];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(LOCALE_KEY_PREFIX) && !keys.includes(k)) {
        keys.push(k);
      }
    }
    for (const k of keys) {
      const raw = localStorage.getItem(k);
      if (raw && normalizeLocale(raw) === "en") return "en";
    }
  } catch {
    // localStorage 不可用时默认中文
  }
  return "zh";
}

function ut(key: string, params?: Record<string, string | number>): string {
  return translate(currentLocale(), key, params);
}

/** 模拟催交 - 判断钉钉绑定状态并发送通知 */
export function handleUrgeSubmit(
  studentName: string,
  subject: string,
  score?: number,
) {
  // 模拟：80%概率已绑定
  const isBound = Math.random() > 0.2;

  if (isBound) {
    toast.success(ut("studentOps.urge.noticeTitle"), {
      description: ut("studentOps.urge.noticeDesc", {
        name: studentName,
        subject,
        scoreNote: score ? ut("studentOps.urge.scoreNote", { score }) : "",
      }),
      duration: 5000,
    });
  } else {
    toast.warning(ut("studentOps.urge.notBoundTitle"), {
      description: ut("studentOps.urge.notBoundDesc", { name: studentName }),
      duration: 4000,
    });
  }
}

/** 模拟联系家长 - 唤起钉钉聊天/发送@消息 */
export function handleContactParent(studentName: string, subject: string) {
  toast.info(ut("studentOps.contact.openTitle"), {
    description: ut("studentOps.contact.openDesc", {
      name: studentName,
      subject,
    }),
    duration: 5000,
  });
}

/** 模拟推送练习 - 生成练习并选择发送方式 */
export function handlePushExercise(studentName: string, subject: string) {
  toast(ut("studentOps.push.generatedTitle"), {
    description: ut("studentOps.push.generatedDesc", {
      name: studentName,
      subject,
    }),
    duration: 5000,
  });
}
