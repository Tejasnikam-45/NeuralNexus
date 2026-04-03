import { useState, useEffect, useRef } from 'react';
import { BASE_URL } from './api_contract';

/**
 * REST API HELPER MODULE
 */

export async function fetchStats() {
  const res = await fetch(`${BASE_URL}/stats`);
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
}

export async function fetchModelPerformance() {
  const res = await fetch(`${BASE_URL}/model/performance`);
  if (!res.ok) throw new Error('Failed to fetch model performance');
  return res.json();
}

export async function fetchTransactionsRecent(limit = 50) {
  const res = await fetch(`${BASE_URL}/transactions/recent?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch recent transactions');
  return res.json();
}

export async function fetchATOChains() {
  const res = await fetch(`${BASE_URL}/ato/chains`);
  if (!res.ok) throw new Error('Failed to fetch ato chains');
  return res.json();
}

export async function fetchFeedbackQueue(limit = 100) {
  const res = await fetch(`${BASE_URL}/feedback/queue?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch feedback queue');
  return res.json();
}

export async function simulateTransactions(n = 10, fraud_pct = 0.3) {
  const res = await fetch(`${BASE_URL}/simulate?n=${n}&fraud_pct=${fraud_pct}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to simulate');
  return res.json();
}

export async function submitFeedback(payload) {
  const res = await fetch(`${BASE_URL}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error('Failed to submit feedback');
  return res.json();
}

/**
 * WEBSOCKET HOOK
 */
export function useLiveWebSocket() {
  const [messages, setMessages] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const ws = useRef(null);

  useEffect(() => {
    const wsUrl = BASE_URL.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws/live';
    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => setIsConnected(true);
    ws.current.onclose = () => setIsConnected(false);
    
    ws.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'transaction') {
            setMessages(prev => [data.data, ...prev].slice(0, 100)); // Keep last 100
        } else if (data.type === 'snapshot') {
            setMessages(data.data);
        }
      } catch (e) {
        console.error("WS Parse error", e);
      }
    };

    return () => {
      if (ws.current) ws.current.close();
    };
  }, []);

  return { messages, isConnected, setMessages };
}
