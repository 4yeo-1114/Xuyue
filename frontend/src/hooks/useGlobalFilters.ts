import { useSyncExternalStore, useCallback } from "react";
import { getSubjectsBySchoolLevel } from "@/components/SubjectTabs";
import { denormalizeGrade } from "@/i18n";

const STORAGE_KEY = "global-teaching-filters";

export interface GlobalFilters {
  schoolLevel: string;
  grade: string;
  selectedClass: string;
  selectedSubject: string;
}

const DEFAULTS: GlobalFilters = {
  schoolLevel: "primary",
  grade: "三年级",
  selectedClass: "",
  selectedSubject: "语文",
};

function loadFilters(): GlobalFilters {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      // 历史版本可能把「规范值」（小学三年级/初一）写进了 grade，与年级下拉 value（三年级/七年级）不匹配会导致下拉为空，加载时拉回原始写法
      return { ...DEFAULTS, ...parsed, grade: denormalizeGrade(parsed.grade) };
    }
  } catch {
    // ignore
  }
  return DEFAULTS;
}

function saveFilters(filters: GlobalFilters) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
  } catch {
    // ignore
  }
}

/* ── 全局单一状态源 ──────────────────────────────────────────────
 * 修复 bug：此前每个组件调用 useGlobalFilters 都拿一份独立的 useState
 * 副本（各自 mount 时读一次 localStorage 就冻结），顶部切科目只更新
 * Index 手里那份，「开始批改」建文件夹读的是 GradingStartPage 自己手里
 * 的旧副本 → 科目标签永远是旧值（默认语文）；且各副本互写 localStorage
 * 会互相覆盖。现在全部组件共享同一份状态，任何一处修改即全局同步。
 */
let current: GlobalFilters = loadFilters();
const listeners = new Set<() => void>();

function setFilters(updater: (prev: GlobalFilters) => GlobalFilters) {
  const next = updater(current);
  // 引用不变（无实际变更）时不通知，避免多余重渲染
  if (next === current) return;
  current = next;
  saveFilters(current);
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): GlobalFilters {
  return current;
}

export function useGlobalFilters(lockedSubject?: string) {
  const filters = useSyncExternalStore(subscribe, getSnapshot);

  const setSchoolLevel = useCallback(
    (schoolLevel: string) => {
      setFilters((prev) => {
        // Reset class when school level changes
        const newSubjects = getSubjectsBySchoolLevel(schoolLevel);
        const subjectStillExists = newSubjects.some(
          (s) => s.name === prev.selectedSubject,
        );
        return {
          ...prev,
          schoolLevel,
          selectedClass: "",
          // 科目锁定时（单科老师端）不随学段切换重置，保持恒定
          selectedSubject:
            lockedSubject ??
            (subjectStillExists
              ? prev.selectedSubject
              : newSubjects[0]?.name || "语文"),
        };
      });
    },
    [lockedSubject],
  );

  const setGrade = useCallback((grade: string) => {
    setFilters((prev) => ({
      ...prev,
      grade,
      selectedClass: "",
    }));
  }, []);

  const setSelectedClass = useCallback((selectedClass: string) => {
    setFilters((prev) => ({ ...prev, selectedClass }));
  }, []);

  const setSelectedSubject = useCallback(
    (selectedSubject: string) => {
      if (lockedSubject) return; // 科目锁定：no-op
      setFilters((prev) => ({ ...prev, selectedSubject }));
    },
    [lockedSubject],
  );

  /** Bulk update (e.g. syncing from class record) without triggering cascading resets */
  const syncFromClass = useCallback(
    (classRecord: { school_level: string; grade: string; id: string }) => {
      setFilters((prev) => ({
        ...prev,
        schoolLevel: classRecord.school_level,
        grade: denormalizeGrade(classRecord.grade),
        selectedClass: classRecord.id,
      }));
    },
    [],
  );

  return {
    ...filters,
    selectedSubject: lockedSubject ?? filters.selectedSubject,
    setSchoolLevel,
    setGrade,
    setSelectedClass,
    setSelectedSubject,
    syncFromClass,
  };
}
