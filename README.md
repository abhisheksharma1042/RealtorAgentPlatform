# DFW Realtor Agent Platform

An AI-powered real estate research platform for the Dallas-Fort Worth metroplex that enables novice real estate license holders to ask natural language questions about market data, comparable sales, and investment trends.

## Features

- 🤖 **AI-Powered Agent**: Claude 4.5 Sonnet with LangGraph orchestration
- 💬 **Natural Language Queries**: Ask questions in plain English
- 📊 **Interactive Visualizations**: Dynamic charts and maps for market insights
- 🗺️ **Geospatial Analysis**: PostGIS-powered location-based queries
- 📈 **Market Reports**: Comprehensive market analysis and trends
- 🔐 **Multi-User Support**: Secure authentication with session persistence

## Tech Stack

### Frontend
- React 18 + TypeScript
- Vite (build tool)
- shadcn/ui + Tailwind CSS
- ECharts (visualizations)
- Mapbox GL (mapping)
- Vercel AI SDK (streaming)

### Backend
- Python 3.11+
- FastAPI
- LangGraph (agent orchestration)
- Anthropic Claude API
- Supabase (PostgreSQL + PostGIS)

## Project Structure

```
RealtorAgentPlatform/
├── frontend/           # React + Vite frontend
│   ├── src/
│   │   ├── components/
│   │   ├── lib/
│   │   └── App.tsx
│   └── package.json
├── backend/            # FastAPI backend
│   ├── agent/          # LangGraph agent logic
│   ├── api/            # API routes
│   ├── db/             # Database client
│   └── main.py
├── shared/             # Shared types and utilities
└── README.md
```

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Supabase account
- Anthropic API key
- Mapbox API key

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Fill in your API keys
uvicorn main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local  # Fill in your API keys
npm run dev
```

Visit http://localhost:5173 to see the application.

## Environment Variables

### Backend (.env)
```
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
TRERC_API_KEY=trerc_xxx (optional)
```

### Frontend (.env.local)
```
VITE_SUPABASE_URL=https://xxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
VITE_MAPBOX_TOKEN=pk.eyJ...
VITE_API_URL=http://localhost:8000
```

## Deployment

- **Frontend**: Vercel (auto-deploy from main branch)
- **Backend**: Railway (Dockerized Python service)

## Development Roadmap

- [x] Phase 0: Project setup
- [ ] Phase 1: Backend agent with mock data
- [ ] Phase 2: Frontend three-pane UI
- [ ] Phase 3: Database schema and sample data
- [ ] Phase 4: Connect agent to real data
- [ ] Phase 5: Visualization layer
- [ ] Phase 6: Interactive filters
- [ ] Phase 7: Authentication
- [ ] Phase 8: Advanced agent features
- [ ] Phase 9: Polish and performance
- [ ] Phase 10: Production deployment
- [ ] Phase 11: TRERC MLS integration

## License

MIT
