import { Textarea } from '@/components/ui/textarea';
import LoadingButton from '@/components/ui/loading-button';

// ----------------------------------------------------------------------

type ChatComposerProps = {
  value: string;
  loading: boolean;
  disabled?: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
};

export default function ChatComposer({
  value,
  loading,
  disabled,
  onChange,
  onSubmit,
}: ChatComposerProps) {
  return (
    <>
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Ask a question about your documents... (Enter to send, Shift+Enter for newline)"
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            onSubmit();
          }
        }}
        className="min-h-16"
        disabled={loading || disabled}
      />

      <LoadingButton
        type="button"
        loading={loading}
        onClick={onSubmit}
        className="shrink-0"
        disabled={disabled}
      >
        Send
      </LoadingButton>
    </>
  );
}
