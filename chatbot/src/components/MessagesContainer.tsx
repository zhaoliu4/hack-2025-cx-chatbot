import React from 'react';
import type { RefObject } from 'react';
import { QRCodeSVG } from 'qrcode.react';

interface Message {
  text: string;
  isUser: boolean;
  timestamp: Date;
  qrCode?: string;
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
  // Function to format text with line breaks
  const formatText = (text: string) => {
    return text.split('\n').map((line, i) => (
      <React.Fragment key={i}>
        {line}
        {i < text.split('\n').length - 1 && <br />}
      </React.Fragment>
    ));
  };

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
            <div className="message-text">
              {formatText(message.text)}
            </div>
            {message.qrCode && (
              <div className="qr-code-container">
                <QRCodeSVG value={message.qrCode} size={200} />
              </div>
            )}
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