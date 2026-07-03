import { useState } from 'react';

import type { LayoutElement, LayoutPage } from './types';
import {
  computeSectionPageRegion,
  type SectionStudyScope,
} from '../study-companion/section-scope';

// ----------------------------------------------------------------------

const LABEL_COLORS: Record<string, string> = {
  title: 'border-blue-500 bg-blue-500/20',
  section_header: 'border-indigo-500 bg-indigo-500/20',
  paragraph: 'border-emerald-500 bg-emerald-500/20',
  text: 'border-emerald-500 bg-emerald-500/20',
  table: 'border-amber-500 bg-amber-500/20',
  picture: 'border-rose-500 bg-rose-500/20',
  caption: 'border-purple-500 bg-purple-500/20',
  list_item: 'border-cyan-500 bg-cyan-500/20',
  page_header: 'border-slate-400 bg-slate-400/15',
  page_footer: 'border-slate-400 bg-slate-400/15',
};

export function boxStyle(
  element: LayoutElement,
  page: LayoutPage,
  imageWidth: number,
  imageHeight: number
) {
  const scaleX = imageWidth / page.width;
  const scaleY = imageHeight / page.height;
  const { bbox } = element;

  return {
    left: `${bbox.l * scaleX}px`,
    top: `${(page.height - bbox.t) * scaleY}px`,
    width: `${(bbox.r - bbox.l) * scaleX}px`,
    height: `${(bbox.t - bbox.b) * scaleY}px`,
  };
}

export function labelClass(label: string): string {
  const key = label.toLowerCase().replace(/\s+/g, '_');
  return LABEL_COLORS[key] ?? 'border-orange-500 bg-orange-500/20';
}

type LayoutPageViewProps = {
  page: LayoutPage;
  compact?: boolean;
  /** Study mode: one soft region for the whole section (incl. children). */
  studyScope?: SectionStudyScope | null;
};

export function LayoutPageView({
  page,
  compact = false,
  studyScope = null,
}: LayoutPageViewProps) {
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const imageSrc = page.image_base64 ? `data:image/jpeg;base64,${page.image_base64}` : null;
  const hovered = page.elements.find((element) => element.id === hoveredId) ?? null;
  const studyMode = studyScope !== null;

  const sectionRegion =
    studyMode && imageSize && studyScope
      ? computeSectionPageRegion(
          page,
          imageSize.width,
          imageSize.height,
          studyScope,
          page.page_no
        )
      : null;

  return (
    <div className={`rounded-lg flex flex-col items-center border bg-muted/20 ${compact ? 'p-2' : 'p-3'}`}>
      <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
        <span>Page {page.page_no}</span>
        {studyMode ? (
          <span className="text-primary">In this section</span>
        ) : (
          <span>
            {page.width.toFixed(0)} × {page.height.toFixed(0)} pt · {page.elements.length} elements
          </span>
        )}
      </div>

      {imageSrc ? (
        <div className="relative inline-block max-w-full overflow-auto">
          <img
            src={imageSrc}
            alt={`Page ${page.page_no}`}
            className="block max-w-full rounded border"
            onLoad={(event) => {
              const img = event.currentTarget;
              setImageSize({ width: img.clientWidth, height: img.clientHeight });
            }}
          />

          {imageSize && studyMode && sectionRegion ? (
            <>
              {sectionRegion.topPx > 0 ? (
                <div
                  className="pointer-events-none absolute inset-x-0 bg-neutral-900/55"
                  style={{ top: 0, height: `${sectionRegion.topPx}px` }}
                />
              ) : null}

              <div
                className="pointer-events-none absolute rounded-sm border-2 border-primary bg-primary/18 shadow-[inset_0_0_0_1px_rgba(var(--primary),0.25)]"
                style={{
                  left: 0,
                  top: `${sectionRegion.topPx}px`,
                  width: `${imageSize.width}px`,
                  height: `${sectionRegion.heightPx}px`,
                }}
              />

              {sectionRegion.topPx + sectionRegion.heightPx < imageSize.height ? (
                <div
                  className="pointer-events-none absolute inset-x-0 bg-neutral-900/55"
                  style={{
                    top: `${sectionRegion.topPx + sectionRegion.heightPx}px`,
                    height: `${imageSize.height - sectionRegion.topPx - sectionRegion.heightPx}px`,
                  }}
                />
              ) : null}

              {sectionRegion.label ? (
                <div
                  className="pointer-events-none absolute left-2 max-w-[90%] truncate rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground shadow-sm"
                  style={{ top: `${Math.max(sectionRegion.topPx + 4, 4)}px` }}
                >
                  {sectionRegion.label}
                </div>
              ) : null}
            </>
          ) : null}

          {imageSize && !studyMode
            ? page.elements.map((element) => (
                <button
                  key={element.id}
                  type="button"
                  aria-label={`${element.label}: ${element.text || 'No text'}`}
                  className={`absolute border-2 transition-opacity hover:opacity-90 ${labelClass(element.label)} ${
                    hoveredId === element.id ? 'opacity-100 ring-2 ring-primary' : 'opacity-70'
                  }`}
                  style={boxStyle(element, page, imageSize.width, imageSize.height)}
                  onMouseEnter={() => setHoveredId(element.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onFocus={() => setHoveredId(element.id)}
                  onBlur={() => setHoveredId(null)}
                />
              ))
            : null}
        </div>
      ) : (
        <div className="rounded border border-dashed p-4 text-center text-sm text-muted-foreground">
          Page image unavailable{studyMode ? '' : ' — showing element list only'}.
        </div>
      )}

      {!studyMode && hovered ? (
        <div className="mt-2 rounded-md border bg-background p-2 text-xs">
          <div className="font-medium capitalize">{hovered.label.replace(/_/g, ' ')}</div>
          {hovered.text ? <div className="mt-1 text-muted-foreground">{hovered.text}</div> : null}
        </div>
      ) : null}

      {!studyMode && !imageSrc && page.elements.length > 0 ? (
        <ul className="mt-2 space-y-1 text-xs">
          {page.elements.map((element) => (
            <li key={element.id} className="rounded border px-2 py-1">
              <span className="font-medium capitalize">{element.label.replace(/_/g, ' ')}</span>
              {element.text ? (
                <span className="text-muted-foreground"> — {element.text}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
