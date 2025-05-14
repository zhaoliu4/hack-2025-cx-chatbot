import React from 'react';

interface RestartChatButtonProps {
  onRestart: () => void;
}

const RestartChatButton: React.FC<RestartChatButtonProps> = ({ onRestart }) => {
  return (
    <button onClick={onRestart} className="new-chat-button">
      <svg 
        width="16" 
        height="16" 
        viewBox="0 0 24 24" 
        fill="none" 
        stroke="currentColor" 
        strokeWidth="2"
        strokeLinecap="round" 
        strokeLinejoin="round"
      >
        <path d="M21 2v6h-6" />
        <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
        <path d="M3 22v-6h6" />
        <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
      </svg>
      Restart Chat
    </button>
  );
};

export default RestartChatButton; 