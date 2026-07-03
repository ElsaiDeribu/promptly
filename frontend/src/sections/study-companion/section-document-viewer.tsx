import { useEffect, useMemo, useRef } from 'react';
import { FileText } from 'lucide-react';

import { LayoutPageView } from '../multimodal-rag/layout-page-view';

import { getSectionStudyScope } from './section-scope';

import type { DocumentLayout } from '../multimodal-rag/types';
import type { StudySection } from './types';

// ----------------------------------------------------------------------

type SectionDocumentViewerProps = {
  layout: DocumentLayout | null;
  section: StudySection | null;
  allSections: StudySection[];
};

export default function SectionDocumentViewer({
  layout,
  section,
  allSections,
}: SectionDocumentViewerProps) {
  const topRef = useRef<HTMLDivElement>(null);

  const scope = useMemo(() => {
    if (!section) return null;
    return getSectionStudyScope(section, allSections);
  }, [section, allSections]);

  const sectionPages = useMemo(() => {
    if (!layout || !scope) return [];
    return layout.pages.filter(
      (page) => page.page_no >= scope.pageStart && page.page_no <= scope.pageEnd
    );
  }, [layout, scope]);

  useEffect(() => {
    topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [section?.id]);

  if (!layout) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-sm text-muted-foreground">
        Document layout loading…
      </div>
    );
  }

  if (!section || !scope) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center text-sm text-muted-foreground">
        <FileText className="h-8 w-8 opacity-40" />
        <p>Select a section to see where it appears in the document.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={topRef} className="shrink-0 border-b px-3 py-2">
        <div className="text-xs font-medium text-muted-foreground">Source in document</div>
        <div className="truncate text-sm font-medium">{scope.section.title}</div>
        <div className="text-xs text-muted-foreground">
          Pages {scope.pageStart}–{scope.pageEnd}
          {scope.includesChildren ? ' · includes subsections' : ''}
          {sectionPages.length > 0
            ? ` · ${sectionPages.length} page${sectionPages.length === 1 ? '' : 's'}`
            : ''}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-2">
        {sectionPages.length > 0 ? (
          sectionPages.map((page) => (
            <LayoutPageView key={page.page_no} page={page} compact studyScope={scope} />
          ))
        ) : (
          <div className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
            No pages found for this section range.
          </div>
        )}
      </div>
    </div>
  );
}
