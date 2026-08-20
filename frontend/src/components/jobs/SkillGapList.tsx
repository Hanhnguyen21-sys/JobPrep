import { Badge } from "@/components/ui/Badge";
import type { SkillGapItem } from "@/types/job";

interface SkillGapListProps {
  skillGap: SkillGapItem[];
}

// Same grouping idea as ExtractedSkillsList, but the axis that matters
// here is "do you already have it," not category -- category still shows
// via Badge variant, have/missing shows via a checkmark + opacity.
export function SkillGapList({ skillGap }: SkillGapListProps) {
  if (skillGap.length === 0) return null;

  const required = skillGap.filter((s) => s.requirement_level === "required");
  const preferred = skillGap.filter((s) => s.requirement_level === "preferred");

  return (
    <div className="space-y-6">
      {required.length > 0 && <SkillGapGroup title="Required" items={required} />}
      {preferred.length > 0 && (
        <SkillGapGroup title="Preferred" items={preferred} />
      )}
    </div>
  );
}

function SkillGapGroup({
  title,
  items,
}: {
  title: string;
  items: SkillGapItem[];
}) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300">
        {title}
      </h3>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <Badge
            key={item.skill_id}
            variant={item.category === "technical" ? "technical" : "soft"}
            className={item.user_has ? "" : "opacity-50"}
          >
            {item.user_has ? "✓ " : ""}
            {item.name}
          </Badge>
        ))}
      </div>
    </div>
  );
}
