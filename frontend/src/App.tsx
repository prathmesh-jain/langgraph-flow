import { useState } from 'react';
import LangGraphFlowVisualizer from './components/LangGraphFlowVisualizer';



function App() {
  const [streamedText, setStreamedText] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [showGraph] = useState(true);
  const [threadId, setThreadId] = useState<string>('');
  const [autoExpandSubgraphs, setAutoExpandSubgraphs] = useState(true);

  const handleRun = async () => {
    // Generate unique thread_id for this execution
    const newThreadId = `thread_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    setThreadId(newThreadId);

    setLoading(true);
    setStreamedText('');

    try {
      // Start the graph execution and stream text output
      const runResponse = await fetch('http://localhost:8000/demo/run', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          thread_id: newThreadId
        }),
      });

      const runReader = runResponse.body?.getReader();
      const runDecoder = new TextDecoder();

      // Stream text output from /run endpoint
      if (runReader) {
        const runStream = async () => {
          while (true) {
            const { done, value } = await runReader.read();
            if (done) break;

            const chunk = runDecoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6);
                try {
                  const parsed = JSON.parse(data);
                  // Handle output text chunks
                  if (parsed.content) {
                    setStreamedText(prev => prev + parsed.content + '\n');
                  }
                } catch (e) {
                  console.error('Failed to parse SSE data:', e);
                }
              }
            }
          }
        };
        runStream();
      }
    } catch (e) {
      console.error('Failed to run graph:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <div className="bg-white p-4 shadow-md">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <h1 className="text-2xl font-bold">LangGraph Demo</h1>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={autoExpandSubgraphs}
                onChange={(e) => setAutoExpandSubgraphs(e.target.checked)}
                className="w-4 h-4"
              />
              Auto-expand subgraphs
            </label>
            <button
              onClick={handleRun}
              disabled={loading}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
            >
              {loading ? 'Running...' : 'Run Graph'}
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 p-4 overflow-hidden">
        <div className="max-w-full mx-auto h-full" style={{ width: '100%' }}>
          <LangGraphFlowVisualizer
            showGraph={showGraph}
            threadId={threadId}
            autoExpandSubgraphs={autoExpandSubgraphs}
            hideSubgraphAfterProcess={true}
          />

          {streamedText && (
            <div className="mt-4 p-4 bg-white rounded-lg shadow-md border">
              <h2 className="text-lg font-semibold mb-2">Streaming Output:</h2>
              <pre className="whitespace-pre-wrap text-sm">{streamedText}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
