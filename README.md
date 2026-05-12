# Agentic Financial Analyzer

AI-powered financial analysis dashboard with a LangChain ReAct agent for real-time spending insights, anomaly detection, and budget tracking.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js Frontend (:3000)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ Dashboard Tab │  │   Chat Tab   │  │   API Client       │ │
│  │ • KPI Cards   │  │ • SSE Stream │  │ • REST Analytics   │ │
│  │ • Charts      │  │ • Tool Vis.  │  │ • Agent Streaming  │ │
│  │ • Alerts      │  │ • History    │  │                    │ │
│  └──────────────┘  └──────────────┘  └────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                    HTTP / SSE
                            │
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (:8000)                     │
│  ┌─────────────────┐  ┌────────────────────────────────────┐ │
│  │ /analytics/*    │  │ /agent/query (SSE)                 │ │
│  │ REST endpoints  │  │ LangChain ReAct Agent              │ │
│  │ for charts      │  │ 8 Financial Tools                  │ │
│  └────────┬────────┘  │ Groq LLM (Llama 3.1 70B)         │ │
│           │           └──────────┬──────────┬──────────────┘ │
│           │                      │          │                │
│  ┌────────▼──────────────────────▼───┐  ┌──▼──────────────┐ │
│  │     PostgreSQL + pgvector (:5432) │  │  Redis (:6379)  │ │
│  │     500 seeded transactions       │  │  Chat memory    │ │
│  │     8 categories                  │  │  24h TTL        │ │
│  └───────────────────────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Set your API key
```bash
# Edit .env and add your Groq API key
GROQ_API_KEY=gsk_your_actual_key_here
```

### 2. Start all services
```bash
docker-compose up -d
```

### 3. Seed the database
```bash
docker compose exec backend python -m app.seed
```
 
### 4. Start the frontend
```bash
cd frontend
npm install
npm run dev
```

### 5. Open the dashboard
Visit **http://localhost:3000**

## Features

### Dashboard
- **KPI Cards**: Income, expenses, net flow, transaction count
- **Budget Alerts**: Real-time alerts when spending exceeds category budgets
- **Monthly Trends**: Income vs spending area chart
- **Spending by Category**: Color-coded bar chart
- **Top Merchants**: Animated progress bars with visit counts
- **Recent Transactions**: Color-coded transaction list

### AI Chat Agent
- **8 Financial Tools**: Query transactions, spending analysis, trend detection, anomaly detection, merchant analysis, net worth, financial summaries, budget alerts
- **SSE Streaming**: Real-time streaming of agent reasoning steps
- **Tool Visualization**: See which tools the agent uses in real-time
- **Redis Memory**: Conversation history persists across sessions (24h TTL)
- **Suggested Queries**: Quick-start prompts for new users

### Backend API
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/agent/query` | POST | SSE streaming agent query |
| `/analytics/spending-by-category` | GET | Category breakdown |
| `/analytics/monthly-trends` | GET | Monthly income/spending |
| `/analytics/net-worth` | GET | Income vs expenses summary |
| `/analytics/top-merchants` | GET | Top merchants by spend |
| `/analytics/budget-alerts` | GET | Budget overspend alerts |
| `/analytics/recent-transactions` | GET | Latest transactions |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, Recharts, Framer Motion, Tailwind CSS 4 |
| Backend | FastAPI, LangChain, Groq LLM (Llama 3.1 70B) |
| Database | PostgreSQL with pgvector |
| Cache | Redis with 24h TTL session memory |
| Infra | Docker Compose |

## Benchmarking

```bash
pip install httpx
python benchmark.py
```

Sends 50 financial queries and reports p50/p95/p99 latency and accuracy.
