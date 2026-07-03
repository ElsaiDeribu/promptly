import type { LayoutElement, LayoutPage } from '../multimodal-rag/types';
import type { StudySection } from './types';

// ----------------------------------------------------------------------

const HEADER_LABELS = new Set(['title', 'section_header', 'document_index']);

export type SectionStudyScope = {
  section: StudySection;
  pageStart: number;
  pageEnd: number;
  includesChildren: boolean;
  /** Next top-level section — marks where the current section ends. */
  nextSection: StudySection | null;
};

function normalizeText(value: string): string {
  return value.toLowerCase().replace(/\s+/g, ' ').trim();
}

function textsMatch(a: string, b: string): boolean {
  const left = normalizeText(a);
  const right = normalizeText(b);
  if (!left || !right) return false;
  return left.includes(right) || right.includes(left);
}

export function getDescendantSections(
  sectionId: string,
  sections: StudySection[]
): StudySection[] {
  const children = sections.filter((s) => s.parent_id === sectionId);
  return children.flatMap((child) => [child, ...getDescendantSections(child.id, sections)]);
}

/** Top-level sections only — the units you study as a whole. */
export function getStudyOutlineSections(sections: StudySection[]): StudySection[] {
  const topLevel = sections.filter((s) => s.level === 1);
  if (topLevel.length > 0) {
    return [...topLevel].sort((a, b) => a.order - b.order);
  }
  const roots = sections.filter((s) => !s.parent_id);
  return [...roots].sort((a, b) => a.order - b.order);
}

/** A study section spans itself and every descendant subsection as one unit. */
export function getSectionStudyScope(
  section: StudySection,
  sections: StudySection[]
): SectionStudyScope {
  const descendants = getDescendantSections(section.id, sections);
  const scoped = [section, ...descendants];
  const studySections = getStudyOutlineSections(sections);
  const index = studySections.findIndex((s) => s.id === section.id);
  const nextSection =
    index >= 0 && index < studySections.length - 1 ? studySections[index + 1] : null;

  return {
    section,
    pageStart: Math.min(...scoped.map((s) => s.page_start)),
    pageEnd: Math.max(...scoped.map((s) => s.page_end)),
    includesChildren: descendants.length > 0,
    nextSection,
  };
}

function isHeaderElement(element: LayoutElement): boolean {
  const label = element.label.toLowerCase().replace(/\s+/g, '_');
  return HEADER_LABELS.has(label);
}

function findSectionHeader(page: LayoutPage, sectionTitle: string): LayoutElement | null {
  for (const element of page.elements) {
    if (!isHeaderElement(element)) continue;
    if (textsMatch(element.text, sectionTitle)) return element;
  }
  return page.elements.find((element) => isHeaderElement(element)) ?? null;
}

function elementTopPx(element: LayoutElement, page: LayoutPage, scaleY: number): number {
  return (page.height - element.bbox.t) * scaleY;
}

function elementBottomPx(element: LayoutElement, page: LayoutPage, scaleY: number): number {
  return (page.height - element.bbox.b) * scaleY;
}

export type SectionPageRegion = {
  topPx: number;
  heightPx: number;
  label?: string;
};

export function computeSectionPageRegion(
  page: LayoutPage,
  imageWidth: number,
  imageHeight: number,
  scope: SectionStudyScope,
  pageNo: number
): SectionPageRegion | null {
  const scaleY = imageHeight / page.height;
  const isFirst = pageNo === scope.pageStart;
  const isLast = pageNo === scope.pageEnd;

  let topPx = 0;
  let bottomPx = imageHeight;

  if (isFirst) {
    const header = findSectionHeader(page, scope.section.title);
    topPx = header ? Math.max(0, elementTopPx(header, page, scaleY) - 6) : 0;
  }

  if (isLast) {
    const nextStartsHere =
      scope.nextSection !== null && scope.nextSection.page_start === pageNo;

    if (nextStartsHere && scope.nextSection) {
      const nextHeader = findSectionHeader(page, scope.nextSection.title);
      if (nextHeader) {
        bottomPx = Math.max(topPx + 8, elementTopPx(nextHeader, page, scaleY) - 4);
      }
    } else {
      const contentBottom = page.elements.reduce((max, element) => {
        const elTop = elementTopPx(element, page, scaleY);
        if (elTop < topPx - 2) return max;
        if (
          scope.nextSection &&
          isHeaderElement(element) &&
          textsMatch(element.text, scope.nextSection.title)
        ) {
          return max;
        }
        return Math.max(max, elementBottomPx(element, page, scaleY));
      }, topPx);

      bottomPx = Math.min(imageHeight, Math.max(contentBottom + 6, topPx + 24));
    }
  }

  if (!isFirst && !isLast) {
    topPx = 0;
    bottomPx = imageHeight;
  }

  const heightPx = Math.min(imageHeight - topPx, Math.max(bottomPx - topPx, 32));

  return {
    topPx,
    heightPx,
    label: isFirst ? scope.section.title : undefined,
  };
}
