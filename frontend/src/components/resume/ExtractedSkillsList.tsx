import { Badge } from "@/components/ui/Badge";
import type { Skill } from "@/types/skill";

interface ExtractedSkillsListProps {
  skills: Skill[];
}

export function ExtractedSkillsList({ skills }: ExtractedSkillsListProps) {
  if (skills.length === 0) return null;

  const technical = skills.filter((s) => s.category === "technical");
  const soft = skills.filter((s) => s.category === "soft");

  return (
    <div className="space-y-6">
      {technical.length > 0 && (
        <SkillGroup
          title="Technical skills"
          skills={technical}
          variant="technical"
        />
      )}
      {soft.length > 0 && (
        <SkillGroup title="Soft skills" skills={soft} variant="soft" />
      )}
    </div>
  );
}

function SkillGroup({
  title,
  skills,
  variant,
}: {
  title: string;
  skills: Skill[];
  variant: "technical" | "soft";
}) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-ink">{title}</h3>
      <div className="flex flex-wrap gap-2">
        {skills.map((skill) => (
          <Badge key={skill.id} variant={variant}>
            {skill.name}
          </Badge>
        ))}
      </div>
    </div>
  );
}
