import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import axios, { endpoints } from '@/utils/axios';
import LoadingButton from '@/components/ui/loading-button';
import { Button } from '@/components/ui/button';
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable';
import { Textarea } from '@/components/ui/textarea';
import {
  Card,
  CardTitle,
  CardHeader,
  CardContent,
  CardDescription,
} from '@/components/ui/card';

import { useDocumentLayout } from '../multimodal-rag/use-document-layout';
import { resolveErrorMessage } from '../multimodal-rag/utils';

import SectionOutline from './section-outline';
import SectionStudyPanel from './section-study-panel';
import SectionDocumentViewer from './section-document-viewer';
import { getSectionStudyScope, getStudyOutlineSections } from './section-scope';
import { useStudyOutline } from './use-study-outline';
import { useStudyProgress } from './use-study-progress';
import { useSectionStudy } from './use-section-study';
import { paths } from '@/routes/paths';

import type { StudySection } from './types';

// ----------------------------------------------------------------------

type StudyCompanionViewProps = {
  documentId?: string;
  /** When true, back navigation clears the selected document. */
  embedded?: boolean;
  onDeselect?: () => void;
};

export default function StudyCompanionView({
  documentId = '',
  embedded = false,
  onDeselect,
}: StudyCompanionViewProps) {
  const navigate = useNavigate();

  const layout = useDocumentLayout();
  const outline = useStudyOutline();
  const progress = useStudyProgress();

  const [filename, setFilename] = useState('');
  const [selectedSection, setSelectedSection] = useState<StudySection | null>(null);
  const [revisionDraft, setRevisionDraft] = useState('');
  const [initError, setInitError] = useState('');

  const completedIds = useMemo(
    () =>
      new Set(
        Object.entries(progress.progress)
          .filter(([, p]) => p.completed)
          .map(([id]) => id)
      ),
    [progress.progress]
  );

  const selectedScope = useMemo(() => {
    if (!selectedSection || !outline.outline?.sections) return null;
    return getSectionStudyScope(selectedSection, outline.outline.sections);
  }, [selectedSection, outline.outline?.sections]);

  const sectionStudy = useSectionStudy({
    documentId,
    section: selectedSection,
    scope: selectedScope,
    filename,
  });

  const studySections = getStudyOutlineSections(outline.outline?.sections ?? []);

  const completedCount = useMemo(
    () => studySections.filter((s) => completedIds.has(s.id)).length,
    [studySections, completedIds]
  );

  const totalSections = studySections.length;

  useEffect(() => {
    if (!documentId) return;

    async function init() {
      setInitError('');
      try {
        const { data } = await axios.get(endpoints.llm.documentDetail(documentId));
        setFilename(data.original_filename);

        await layout.openLayout(documentId, data.original_filename);
        await outline.generateOutline(documentId);
        await progress.refresh(documentId);
      } catch (e) {
        setInitError(resolveErrorMessage(e, 'Failed to load study session'));
      }
    }

    init();

    return () => {
      layout.reset();
      outline.reset();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId]);

  useEffect(() => {
    if (!selectedSection) return;
    sectionStudy.resetSection();
    const cached = progress.progress[selectedSection.id];
    if (cached?.notes) {
      sectionStudy.loadCachedNotes(cached.notes);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSection?.id]);

  async function handleRevise() {
    const instruction = revisionDraft.trim();
    if (!instruction || !documentId) return;
    const result = await outline.reviseOutline(documentId, instruction);
    if (result === 'completed') {
      setRevisionDraft('');
      setSelectedSection(null);
    }
  }

  async function handleGenerateNotes() {
    if (!selectedSection || !documentId) return;
    const generated = await sectionStudy.generateNotes(true);
    if (generated) {
      await progress.saveNotes(documentId, selectedSection.id, generated);
    }
  }

  async function handleMarkComplete(completed: boolean) {
    if (!selectedSection || !documentId) return;
    await progress.markComplete(documentId, selectedSection.id, completed);
    if (completed && sectionStudy.notes) {
      await progress.saveNotes(documentId, selectedSection.id, sectionStudy.notes);
    }
  }

  const isInitializing = layout.loading || outline.loading;
  const error =
    initError ||
    layout.error ||
    outline.error ||
    progress.error ||
    sectionStudy.error;

  if (!documentId) {
    return null;
  }

  function handleBack() {
    if (onDeselect) {
      onDeselect();
      return;
    }
    if (embedded) {
      navigate(`${paths.dashboard.root}?tab=documents`);
      return;
    }
    navigate(-1);
  }

  return (
    <Card className="flex h-full w-full flex-col">
      <CardHeader className="shrink-0">
        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={handleBack}
            className="h-8 w-8"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="min-w-0 flex-1">
            <CardTitle className="truncate text-md">
              {filename || 'Study Companion'}
            </CardTitle>
            <CardDescription>
              {totalSections > 0
                ? `Progress: ${completedCount}/${totalSections} sections`
                : 'Structured study from your document'}
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      {error && (
        <div className="mx-6 mb-2 rounded-md border border-destructive/40 bg-destructive/10 p-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {isInitializing ? (
        <CardContent className="flex flex-1 items-center justify-center gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Preparing study outline…
        </CardContent>
      ) : (
        <CardContent className="flex min-h-0 flex-1 flex-col gap-3 pb-4">
          {outline.outline && (
            <div className="shrink-0 rounded-lg border bg-muted/20 p-3">
              <div className="mb-2 text-sm font-medium">Revise outline</div>
              <div className="flex gap-2">
                <Textarea
                  value={revisionDraft}
                  onChange={(e) => setRevisionDraft(e.target.value)}
                  placeholder='e.g. "Split chapter 3 into two sections" or "Merge sections 1 and 2"'
                  rows={2}
                  className="min-h-0 flex-1 text-sm"
                  disabled={outline.revising}
                />
                <LoadingButton
                  type="button"
                  loading={outline.revising}
                  disabled={!revisionDraft.trim()}
                  onClick={handleRevise}
                  className="shrink-0 self-end"
                >
                  Revise
                </LoadingButton>
              </div>
            </div>
          )}

          <ResizablePanelGroup
            direction="horizontal"
            className="min-h-0 flex-1 rounded-lg border"
          >
            <ResizablePanel defaultSize={40} minSize={22} className="min-h-0">
              <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
                <SectionDocumentViewer
                  layout={layout.layout}
                  section={selectedSection}
                  allSections={outline.outline?.sections ?? []}
                />
              </div>
            </ResizablePanel>

            <ResizableHandle />

            <ResizablePanel defaultSize={20} minSize={15} className="min-h-0">
              <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
                <div className="shrink-0 border-b px-3 py-2 text-xs font-medium text-muted-foreground">
                  Study outline
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto">
                  <SectionOutline
                    sections={outline.outline?.sections ?? []}
                    selectedId={selectedSection?.id ?? null}
                    completedIds={completedIds}
                    onSelect={setSelectedSection}
                  />
                </div>
              </div>
            </ResizablePanel>

            <ResizableHandle />

            <ResizablePanel defaultSize={40} minSize={25} className="min-h-0">
              <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
                <SectionStudyPanel
                  section={selectedSection}
                  scope={selectedScope}
                  notes={sectionStudy.notes}
                  notesLoading={sectionStudy.notesLoading}
                  questions={sectionStudy.questions}
                  questionsLoading={sectionStudy.questionsLoading}
                  chatMessages={sectionStudy.chatMessages}
                  chatLoading={sectionStudy.chatLoading}
                  isCompleted={
                    selectedSection ? completedIds.has(selectedSection.id) : false
                  }
                  onGenerateNotes={handleGenerateNotes}
                  onGenerateQuestions={sectionStudy.generateQuestions}
                  onSendMessage={sectionStudy.sendMessage}
                  onMarkComplete={handleMarkComplete}
                />
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        </CardContent>
      )}
    </Card>
  );
}
