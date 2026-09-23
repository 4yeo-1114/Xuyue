import { useState, useMemo, useRef, useEffect } from "react";
import { Search, FileText, User, Zap, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { NAV_ITEMS } from "@/components/Sidebar";
import { useStudents } from "@/hooks/useStudents";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import { HOME_ACTION_KEYWORDS, HOME_MODULE_KEYWORDS } from "@/i18n/locales/modules/home";

/* ── Quick actions ── */
interface QuickAction {
  id: string;
  labelKey: string;
  actionType: "nav" | "callback";
  navId?: string;
  callbackId?: string;
}

const QUICK_ACTION_DEFS: QuickAction[] = [
  { id: "grade-photo", labelKey: "home.search.action.gradePhoto", actionType: "callback", callbackId: "upload" },
  { id: "grade-upload", labelKey: "home.search.action.gradeUpload", actionType: "callback", callbackId: "upload" },
  { id: "gen-exam", labelKey: "home.search.action.genExam", actionType: "nav", navId: "prep-exam" },
  { id: "gen-courseware", labelKey: "home.search.action.genCourseware", actionType: "nav", navId: "prep-compose" },
  { id: "wrong-q", labelKey: "home.search.action.wrongQ", actionType: "nav", navId: "class-students" },
];

/* ── Flat module list ── */
interface FlatModule {
  id: string;
  label: string;
  groupLabel: string;
  icon: React.ElementType;
}

/* ── Props ── */
interface GlobalSearchBarProps {
  selectedClass?: string;
  onNavChange: (id: string) => void;
  onNavigateToStudent: (name: string) => void;
  onUploadClick: () => void;
}

export function GlobalSearchBar({ selectedClass, onNavChange, onNavigateToStudent, onUploadClick }: GlobalSearchBarProps) {
  const { t, locale } = useLocale();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: students = [] } = useStudents(selectedClass);

  const allModules = useMemo((): FlatModule[] => {
    const result: FlatModule[] = [];
    for (const group of NAV_ITEMS) {
      if (group.children) {
        for (const child of group.children) {
          result.push({
            id: child.id,
            label: t(`nav.${child.id}`, undefined, child.label),
            groupLabel: t(`nav.${group.id}`, undefined, group.label),
            icon: child.icon,
          });
        }
      } else {
        result.push({
          id: group.id,
          label: t(`nav.${group.id}`, undefined, group.label),
          groupLabel: "",
          icon: group.icon,
        });
      }
    }
    return result;
  }, [t, locale]);

  const quickActions = useMemo(
    () => QUICK_ACTION_DEFS.map((a) => ({ ...a, label: t(a.labelKey) })),
    [t, locale]
  );

  const moduleKeywords = HOME_MODULE_KEYWORDS[locale];
  const actionKeywords = HOME_ACTION_KEYWORDS[locale];

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const trimmed = query.trim().toLowerCase();

  const matchedModules = useMemo(() => {
    if (!trimmed) return [];
    return allModules.filter((m) => {
      if (m.label.toLowerCase().includes(trimmed)) return true;
      const kws = moduleKeywords[m.id];
      return kws?.some((k) => k.toLowerCase().includes(trimmed));
    }).slice(0, 5);
  }, [trimmed, allModules, moduleKeywords]);

  const matchedStudents = useMemo(() => {
    if (!trimmed || !students.length) return [];
    return students.filter((s) => s.name.toLowerCase().includes(trimmed)).slice(0, 5);
  }, [trimmed, students]);

  const matchedActions = useMemo(() => {
    if (!trimmed) return [];
    return quickActions.filter((a) =>
      a.label.toLowerCase().includes(trimmed) || actionKeywords[a.id]?.some((k) => k.toLowerCase().includes(trimmed))
    ).slice(0, 4);
  }, [trimmed, quickActions, actionKeywords]);

  const hasResults = matchedModules.length > 0 || matchedStudents.length > 0 || matchedActions.length > 0;
  const showDropdown = open && trimmed.length > 0;

  const handleSelect = (type: "module" | "student" | "action", item: any) => {
    setQuery("");
    setOpen(false);
    if (type === "module") {
      onNavChange(item.id);
    } else if (type === "student") {
      onNavigateToStudent(item.name);
    } else if (type === "action") {
      const action = item as QuickAction & { label: string };
      if (action.actionType === "nav" && action.navId) {
        onNavChange(action.navId);
      } else if (action.callbackId === "upload") {
        onUploadClick();
      }
    }
  };

  return (
    <div ref={containerRef} className="relative" data-tour="global-search">
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground pointer-events-none" />
        <Input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => { if (trimmed) setOpen(true); }}
          placeholder={t("home.search.placeholder")}
          className="pl-12 pr-10 h-12 text-base rounded-xl bg-muted/50 border-border/60 focus-visible:ring-primary/30 shadow-sm"
        />
        {query && (
          <button
            onClick={() => { setQuery(""); setOpen(false); }}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {showDropdown && (
        <div className="absolute z-50 top-full mt-2 w-full rounded-xl border border-border bg-popover shadow-lg overflow-hidden animate-in fade-in-0 zoom-in-95 duration-150">
          {!hasResults ? (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">
              {t("home.search.noResults", { query })}
            </div>
          ) : (
            <div className="max-h-[320px] overflow-y-auto py-1">
              {/* Modules */}
              {matchedModules.length > 0 && (
                <div>
                  <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5" /> {t("home.search.sectionModules")}
                  </div>
                  {matchedModules.map((m) => {
                    const Icon = m.icon;
                    return (
                      <button
                        key={m.id}
                        onClick={() => handleSelect("module", m)}
                        className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-foreground hover:bg-accent transition-colors"
                      >
                        <Icon className="w-4 h-4 text-primary shrink-0" />
                        <span className="font-medium">{m.label}</span>
                        {m.groupLabel && (
                          <span className="text-xs text-muted-foreground ml-auto">{m.groupLabel}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Students */}
              {matchedStudents.length > 0 && (
                <div>
                  <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground flex items-center gap-1.5 border-t border-border/40">
                    <User className="w-3.5 h-3.5" /> {t("home.search.sectionStudents")}
                  </div>
                  {matchedStudents.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => handleSelect("student", s)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-foreground hover:bg-accent transition-colors"
                    >
                      <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-xs font-medium text-primary shrink-0">
                        {s.name[0]}
                      </div>
                      <span>{s.name}</span>
                      <span className="text-xs text-muted-foreground ml-auto">
                        {t("home.search.studentNumber", { number: s.student_number })}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {/* Quick actions */}
              {matchedActions.length > 0 && (
                <div>
                  <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground flex items-center gap-1.5 border-t border-border/40">
                    <Zap className="w-3.5 h-3.5" /> {t("home.search.sectionActions")}
                  </div>
                  {matchedActions.map((a) => (
                    <button
                      key={a.id}
                      onClick={() => handleSelect("action", a)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-foreground hover:bg-accent transition-colors"
                    >
                      <Zap className="w-4 h-4 text-primary shrink-0" />
                      <span>{a.label}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
