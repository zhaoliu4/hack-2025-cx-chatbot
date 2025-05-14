import React from 'react';
import type { KeyboardEvent } from 'react';

interface ChatInputProps {
  inputMessage: string;
  onInputChange: (value: string) => void;
  onSendMessage: () => void;
}

const MAX_CHARS = 500;

const ChatInput: React.FC<ChatInputProps> = ({
  inputMessage,
  onInputChange,
  onSendMessage
}) => {
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSendMessage();
    }
  };

  return (
    <div className="input-container" role="form" aria-label="Chat message input">
      <input
        type="text"
        value={inputMessage}
        onChange={(e) => onInputChange(e.target.value.slice(0, MAX_CHARS))}
        onKeyDown={handleKeyDown}
        placeholder="Type your message..."
        className="chat-input"
        aria-label="Message input"
        role="textbox"
        aria-multiline="false"
        maxLength={MAX_CHARS}
      />
      <button 
        onClick={onSendMessage} 
        className="send-button"
        aria-label="Send message"
        disabled={!inputMessage.trim()}
      >
        <img src="/send.png" alt="Send" className="send-icon" />
      </button>
    </div>
  );
};

export default ChatInput; 