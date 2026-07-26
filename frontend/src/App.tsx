import { useState } from 'react';

const NODES = [
  'input_processor',
  'planner',
  'research_subgraph',
  'direct_executor',
  'analyzer',
  'validator',
  'output_formatter',
];

function App() {
  const [nodeStatus, setNodeStatus] = useState<Record<string, string>>({});
  const [streamedText, setStreamedText] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const handleRun = async () => {
    setLoading(true);
    setNodeStatus({});
    setStreamedText('');
    try {
      const response = await fetch('http://localhost:8000/demo/stream');
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
                if (parsed.type === 'error') {
                  console.error('Server error:', parsed.message);
                  setLoading(false);
                  break;
                } else if (parsed.type === 'graph_started') {
                  setNodeStatus({});
                } else if (parsed.type === 'node_completed') {
                  const nodeId = parsed.data?.node_id;
                  if (nodeId) {
                    setNodeStatus(prev => ({
                      ...prev,
                      [nodeId]: 'completed'
                    }));
                  }
                } else if (parsed.type === 'graph_completed') {
                  setLoading(false);
                }
              } catch (e) {
                console.error('Failed to parse SSE data:', e);
              }
            }
          }
        }
      }
    } catch (e) {
      console.error('Failed to run graph:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleRunWithOutput = async () => {
    setLoading(true);
    setStreamedText('');
    try {
      const response = await fetch('http://localhost:8000/demo/run', {
        method: 'POST',
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
                if (parsed.content) {
                  setStreamedText(prev => prev + parsed.content + '\n');
                }
              } catch (e) {
                console.error('Failed to parse SSE data:', e);
              }
            }
          }
        }
      }
    } catch (e) {
      console.error('Failed to run graph:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-2xl w-full">
        <h1 className="text-2xl font-bold mb-4">LangGraph Demo</h1>
        
        <div className="flex gap-4 mb-6">
          <button
            onClick={handleRun}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
          >
            {loading ? 'Running...' : 'Run Graph (Visualization)'}
          </button>
          <button
            onClick={handleRunWithOutput}
            disabled={loading}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400"
          >
            {loading ? 'Running...' : 'Run Graph (Output)'}
          </button>
        </div>

        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-3">Node Status:</h2>
          <div className="grid grid-cols-2 gap-2">
            {NODES.map(node => (
              <div
                key={node}
                className={`p-3 rounded border-2 ${
                  nodeStatus[node] === 'completed'
                    ? 'bg-green-100 border-green-500'
                    : 'bg-gray-100 border-gray-300'
                }`}
              >
                <div className="font-medium text-sm">{node}</div>
                <div className="text-xs mt-1">
                  {nodeStatus[node] === 'completed' ? '✓ Completed' : '⏳ Pending'}
                </div>
              </div>
            ))}
          </div>
        </div>

        {streamedText && (
          <div className="mt-4 p-4 bg-gray-100 rounded">
            <h2 className="text-lg font-semibold mb-2">Streaming Output:</h2>
            <pre className="whitespace-pre-wrap text-sm">{streamedText}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
