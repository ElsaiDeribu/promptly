import { useSearchParams } from 'react-router-dom';
import LLMChat from '@/pages/dashboard/llm-chat';
import Playground from '@/pages/playground/page';
import MultimodalRag from '@/pages/dashboard/multimodal-rag';
import Documents from '@/pages/dashboard/documents';
import { Tabs, TabsList, TabsContent, TabsTrigger } from '@/components/ui/tabs';

export default function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') ?? 'documents';

  function handleTabChange(value: string) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set('tab', value);
        if (value !== 'documents') {
          next.delete('documentId');
        }
        return next;
      },
      { replace: true }
    );
  }

  return (
    <div className="pt-2">
      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="mx-auto">
          {/* <TabsTrigger value="playground">Playground</TabsTrigger> */}
          {/* <TabsTrigger value="chat">Chat</TabsTrigger> */}
          <TabsTrigger value="documents">Study</TabsTrigger>
          <TabsTrigger value="multimodal-rag">Multimodal RAG</TabsTrigger>
        </TabsList>

        {/* <TabsContent value="playground">
          <Playground />
        </TabsContent> */}

        {/* <TabsContent value="chat">
          <LLMChat />
        </TabsContent> */}

        <TabsContent value="documents">
          <Documents />
        </TabsContent>

        <TabsContent value="multimodal-rag">
          <MultimodalRag />
        </TabsContent>
      </Tabs>
    </div>
  );
}
