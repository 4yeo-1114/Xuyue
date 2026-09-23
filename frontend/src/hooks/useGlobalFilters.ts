import { useState, useEffect, useCallback } from "react";
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

export function useGlobalFilters() {
  const [filters, setFiltersState] = useState<GlobalFilters>(loadFilters);

  // Persist on change
  useEffect(() => {
    saveFilters(filters);
  }, [filters]);

  const setSchoolLevel = useCallback((schoolLevel: string) => {
    setFiltersState((prev) => {
      // Reset class when school level changes
      const newSubjects = getSubjectsBySchoolLevel(schoolLevel);
      const subjectStillExists = newSubjects.some((s) => s.name === prev.selectedSubject);
      return {
        ...prev,
        schoolLevel,
        selectedClass: "",
        selectedSubject: subjectStillExists ? prev.selectedSubject : newSubjects[0]?.name || "语文",
      };
    });
  }, []);

  const setGrade = useCallback((grade: string) => {
    setFiltersState((prev) => ({
      ...prev,
      grade,
      selectedClass: "",
    }));
  }, []);

  const setSelectedClass = useCallback((selectedClass: string) => {
    setFiltersState((prev) => ({ ...prev, selectedClass }));
  }, []);

  const setSelectedSubject = useCallback((selectedSubject: string) => {
    setFiltersState((prev) => ({ ...prev, selectedSubject }));
  }, []);

  /** Bulk update (e.g. syncing from class record) without triggering cascading resets */
  const syncFromClass = useCallback(
    (classRecord: { school_level: string; grade: string; id: string }) => {
      setFiltersState((prev) => ({
        ...prev,
        schoolLevel: classRecord.school_level,
        grade: denormalizeGrade(classRecord.grade),
        selectedClass: classRecord.id,
      }));
    },
    []
  );

  return {
    ...filters,
    setSchoolLevel,
    setGrade,
    setSelectedClass,
    setSelectedSubject,
    syncFromClass,
  };
}
