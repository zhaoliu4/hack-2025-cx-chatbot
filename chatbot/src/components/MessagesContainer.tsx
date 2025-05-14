import React from 'react';
import type { RefObject } from 'react';

interface Message {
  text: string;
  isUser: boolean;
  timestamp: Date;
}

interface MessagesContainerProps {
  messages: Message[];
  isLoading: boolean;
  messagesEndRef: RefObject<HTMLDivElement | null>;
}

const MessagesContainer: React.FC<MessagesContainerProps> = ({
  messages,
  isLoading,
  messagesEndRef
}) => {
  return (
    <div className="messages-container">
      {messages.map((message, index) => (
        <div
          key={index}
          className={`message-row ${message.isUser ? 'user' : 'bot'}`}
        >
          {!message.isUser && (
            <img
              src="/hr_circle_logo_100.png"
              alt="Support Agent"
              className="bot-icon"
            />
          )}
          <div className={`message-bubble ${message.isUser ? 'user' : 'bot'}`}>
            {message.text}
          </div>
        </div>
      ))}
      {isLoading && (
        <div className="loading-dots">
          <div className="loading-dot" />
          <div className="loading-dot" />
          <div className="loading-dot" />
        </div>
      )}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessagesContainer; 