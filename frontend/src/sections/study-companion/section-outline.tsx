import { Check, ChevronRight } from 'lucide-react';

import { getStudyOutlineSections } from './section-scope';

import type { StudySection } from './types';

// ----------------------------------------------------------------------

type SectionOutlineProps = {
  sections: StudySection[];
  selectedId: string | null;
  completedIds: Set<string>;
  onSelect: (section: StudySection) => void;
};

export default function SectionOutline({
  sections,
  selectedId,
  completedIds,
  onSelect,
}: SectionOutlineProps) {
  const studySections = getStudyOutlineSections(sections);

  if (studySections.length === 0) {
    return (
      <div className="p-4 text-sm text-muted-foreground">No study sections yet.</div>
    );
  }

  return (
    <div className="flex flex-col gap-0.5 p-2">
      {studySections.map((section) => {
        const isSelected = section.id === selectedId;
        const isCompleted = completedIds.has(section.id);

        return (
          <button
            key={section.id}
            type="button"
            onClick={() => onSelect(section)}
            className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
              isSelected
                ? 'bg-primary/10 text-primary'
                : 'hover:bg-muted/60 text-foreground'
            }`}
          >
            {isCompleted ? (
              <Check className="h-3.5 w-3.5 shrink-0 text-green-600" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            )}
            <span className="min-w-0 flex-1 truncate">{section.title}</span>
            <span className="shrink-0 text-xs text-muted-foreground">
              p{section.page_start}
            </span>
          </button>
        );
      })}
    </div>
  );
}
