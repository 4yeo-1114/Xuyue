import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useLocale } from "@/contexts/LocaleContext";
import { Info, Search } from "lucide-react";
import { listAdminUsers } from "@/services/api";

export function AdminUsers() {
  const [search, setSearch] = useState("");
  const { t, locale } = useLocale();
  const dateLocale = locale === "en" ? "en-US" : "zh-CN";

  const { data: profiles = [] } = useQuery({
    queryKey: ["admin-profiles"],
    queryFn: async () => {
      const data = await listAdminUsers();
      return [...data].sort((a, b) => {
        const ac = a.created_at || "";
        const bc = b.created_at || "";
        if (ac < bc) return 1;
        if (ac > bc) return -1;
        return 0;
      });
    },
  });

  const filtered = profiles.filter(
    (p: any) =>
      !search ||
      (p.display_name || "").toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div>
      <h2 className="text-xl font-bold text-foreground mb-4">
        {t("admin.users.title")}
      </h2>

      <div className="flex items-start gap-2 mb-4 text-sm text-muted-foreground rounded-lg border border-border bg-muted/40 px-3 py-2.5">
        <Info className="w-4 h-4 shrink-0 mt-0.5" />
        <span>{t("admin.users.roleManagedBackend")}</span>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder={t("admin.users.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Badge variant="secondary">
          {filtered.length}
          {t("admin.users.teacherCountSuffix")}
        </Badge>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("admin.users.table.name")}</TableHead>
                <TableHead>{t("admin.users.table.school")}</TableHead>
                <TableHead>{t("admin.users.table.registeredAt")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((p: any) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">
                    {p.display_name || "—"}
                  </TableCell>
                  <TableCell>
                    {p.school_name || t("admin.users.schoolUnset")}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {new Date(p.created_at).toLocaleDateString(dateLocale)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
