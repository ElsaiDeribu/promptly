import { useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import LoadingButton from '@/components/ui/loading-button';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';

import ChatWindow from '../multimodal-rag/chat-window';
import ChatComposer from '../multimodal-rag/chat-composer';
import { markdownComponents } from '../multimodal-rag/markdown-components';

import type { StudyQuestion, StudySection } from './types';
import type { ChatMessage } from './types';
import type { SectionStudyScope } from './section-scope';

// ----------------------------------------------------------------------

type SectionStudyPanelProps = {
  section: StudySection | null;
  scope: SectionStudyScope | null;
  notes: string;
  notesLoading: boolean;
  questions: StudyQuestion[];
  questionsLoading: boolean;
  chatMessages: ChatMessage[];
  chatLoading: boolean;
  isCompleted: boolean;
  onGenerateNotes: () => void;
  onGenerateQuestions: () => void;
  onSendMessage: (text: string) => void;
  onMarkComplete: (completed: boolean) => void;
};

export default function SectionStudyPanel({
  section,
  scope,
  notes,
  notesLoading,
  questions,
  questionsLoading,
  chatMessages,
  chatLoading,
  isCompleted,
  onGenerateNotes,
  onGenerateQuestions,
  onSendMessage,
  onMarkComplete,
}: SectionStudyPanelProps) {
  const [draft, setDraft] = useState('');
  const [activeTab, setActiveTab] = useState<'notes' | 'questions' | 'chat'>('notes');
  const bottomRef = useRef<HTMLDivElement>(null);

  if (!section) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Select a section from the outline to start studying.
      </div>
    );
  }

  async function handleSend() {
    const text = draft.trim();
    if (!text || chatLoading) return;
    setDraft('');
    setActiveTab('chat');
    await onSendMessage(text);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="font-medium">{section.title}</h3>
            <p className="text-xs text-muted-foreground">
              Pages {scope?.pageStart ?? section.page_start}–{scope?.pageEnd ?? section.page_end}
              {scope?.includesChildren ? ' (full section)' : ''}
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            variant={isCompleted ? 'secondary' : 'default'}
            onClick={() => onMarkComplete(!isCompleted)}
          >
            {isCompleted ? 'Mark incomplete' : 'Mark complete'}
          </Button>
        </div>

        <div className="mt-2 flex gap-1">
          {(['notes', 'questions', 'chat'] as const).map((tab) => (
            <Button
              key={tab}
              type="button"
              size="sm"
              variant={activeTab === tab ? 'default' : 'ghost'}
              onClick={() => setActiveTab(tab)}
              className="h-7 text-xs capitalize"
            >
              {tab}
            </Button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {activeTab === 'notes' && (
          <div className="flex flex-col gap-3">
            <LoadingButton
              type="button"
              size="sm"
              loading={notesLoading}
              onClick={onGenerateNotes}
              className="w-fit"
            >
              {notes ? 'Regenerate notes' : 'Generate notes'}
            </LoadingButton>
            {notes ? (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                  {notes}
                </ReactMarkdown>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Generate study notes for this section on demand.
              </p>
            )}
          </div>
        )}

        {activeTab === 'questions' && (
          <div className="flex flex-col gap-3">
            <LoadingButton
              type="button"
              size="sm"
              loading={questionsLoading}
              onClick={onGenerateQuestions}
              className="w-fit"
            >
              Generate practice questions
            </LoadingButton>
            {questions.length > 0 ? (
              <ol className="flex list-decimal flex-col gap-3 pl-4">
                {questions.map((q, i) => (
                  <li key={i} className="text-sm">
                    <p className="font-medium">{q.question}</p>
                    {q.hint ? (
                      <p className="mt-1 text-xs text-muted-foreground">Hint: {q.hint}</p>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted-foreground">
                Generate practice questions to test your understanding.
              </p>
            )}
          </div>
        )}

        {activeTab === 'chat' && (
          <div className="flex h-full min-h-[300px] flex-col gap-2">
            <ChatWindow messages={chatMessages} bottomRef={bottomRef} />
            <Separator />
            <div className="flex shrink-0 gap-2">
              <ChatComposer
                value={draft}
                loading={chatLoading}
                onChange={setDraft}
                onSubmit={handleSend}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
