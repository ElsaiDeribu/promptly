import LLMChat from '@/pages/dashboard/llm-chat';
import MultimodalRag from '@/pages/dashboard/multimodal-rag';
import Playground from '@/pages/playground/page';
import { Tabs, TabsList, TabsContent, TabsTrigger } from '@/components/ui/tabs';

export default function DashboardPage() {
  return (
    <div className="p-6">
      <Tabs defaultValue="playground" className="w-full">
        <TabsList>
          <TabsTrigger value="playground">Playground</TabsTrigger>
          <TabsTrigger value="chat">Chat</TabsTrigger>
          <TabsTrigger value="multimodal-rag">Multimodal RAG</TabsTrigger>
        </TabsList>

        <TabsContent value="playground">
          <Playground />
        </TabsContent>

        <TabsContent value="chat">
          <LLMChat />
        </TabsContent>

        <TabsContent value="multimodal-rag">
          <MultimodalRag />
        </TabsContent>
      </Tabs>
    </div>
  );
}
