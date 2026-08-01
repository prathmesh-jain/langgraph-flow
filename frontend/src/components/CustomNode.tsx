import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import type { NodeStatus } from '../types';
import { cn } from '../utils';

const statusStyles: Record<NodeStatus, string> = {
  idle: 'border-gray-300 bg-white',
  queued: 'border-yellow-400 bg-yellow-50',
  running: 'border-blue-500 bg-blue-50 animate-pulse shadow-lg shadow-blue-500/50',
  completed: 'border-green-500 bg-green-50',
  failed: 'border-red-500 bg-red-50',
};

const handleStyle = { background: '#9ca3af', width: 8, height: 8 };

const CustomNode = memo(({ data, selected }: NodeProps) => {
  const status: NodeStatus = (data?.status as NodeStatus) || 'idle';
  const label: string = String(data?.label ?? data?.id ?? '');

  return (
    <div
      className={cn(
        'px-4 py-2 rounded-lg border-2 min-w-[120px] text-center transition-all duration-300',
        statusStyles[status] || statusStyles.idle,
        selected && 'ring-2 ring-blue-300 ring-offset-2'
      )}
    >
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="font-medium text-sm text-gray-700 break-words">{label || '\u00A0'}</div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  );
});

CustomNode.displayName = 'CustomNode';

export default CustomNode;
