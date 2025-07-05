import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import { TooltipProvider } from "./context/TooltipContext";

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <TooltipProvider>
      <App />
    </TooltipProvider>
  </React.StrictMode>
);
