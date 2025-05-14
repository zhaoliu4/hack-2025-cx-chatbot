import React from 'react';

interface ChatInputProps {
  inputMessage: string;
  onInputChange: (value: string) => void;
  onSendMessage: () => void;
}

const ChatInput: React.FC<ChatInputProps> = ({
  inputMessage,
  onInputChange,
  onSendMessage
}) => {
  return (
    <div className="input-container">
      <input
        type="text"
        value={inputMessage}
        onChange={(e) => onInputChange(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && onSendMessage()}
        placeholder="Type your message..."
        className="chat-input"
      />
      <button onClick={onSendMessage} className="send-button">
        <img src="/send.png" alt="Send" className="send-icon" />
      </button>
    </div>
  );
};

export default ChatInput; 