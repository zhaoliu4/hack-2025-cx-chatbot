import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/chat': {
        target: 'http://localhost:5174',
        configure: (proxy, options) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            if (req.method === 'POST') {
              // Mock response with QR code for testing
              res.writeHead(200, { 'Content-Type': 'application/json' });
              
              // Example of a return label QR code format
              
              res.end(JSON.stringify({
                chat_id: '123',
                response: 'I\'ve generated a QR code for your return. You can scan this at any Happy Returns location:',
                qrCode: 'HRTESTER'
              }));
            }
          });
        }
      }
    }
  }
})
