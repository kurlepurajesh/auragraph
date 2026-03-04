# AuraGraph - Product Requirements Document

## Project Overview
**Project Title**: AuraGraph: AI That Learns How You Learn  
**Team**: Wowffulls | IIT Roorkee  
**Challenge Area**: AI Study Buddy  
**Date**: June 2, 2025

## Architecture
- **Frontend**: React CRA + Tailwind CSS + Redux Toolkit (port 3000)
- **Backend**: FastAPI + MongoDB (port 8001, /api prefix)
- **AI**: OpenAI GPT-4o via Emergent LLM Key (emergentintegrations library)
- **Design**: Paper/Academic theme - Playfair Display, Manrope, Crimson Pro fonts. Colors: #FDFBF7 (bg), #0F5132 (primary), #8B5CF6 (mutation purple)

## User Personas
1. **Rahul** - Overwhelmed engineering student needing fused notes from slides + textbooks
2. **Ananya** - Top performer wanting depth + targeted practice for weak concepts

## Core Requirements (Static)
1. Knowledge Fusion - Upload slides + textbook PDFs → unified proficiency-tuned notes
2. Dynamic Note Mutation - Highlight confusing text → AI rewrites permanently
3. Cognitive Knowledge Graph - Visual mastery map with green/yellow/red nodes
4. Sniper Examiner - Targeted MCQ practice questions for weak concepts
5. Auth - JWT-based email/password registration and login
6. Notebook Management - CRUD operations with MongoDB persistence

## What's Been Implemented (June 2, 2025)
- [x] Full auth system (register/login with JWT tokens)
- [x] Dashboard with notebook CRUD, search, cards
- [x] Notebook Workspace with dual PDF upload zones (slides + textbook)
- [x] Knowledge Fusion Engine (GPT-4o + local fallback)
- [x] Dynamic Note Mutation with doubt modal & chat log
- [x] Examiner Agent generating targeted MCQs
- [x] Concept Extraction → SVG Knowledge Graph with mastery tracking
- [x] Proficiency Level selector (Beginner/Intermediate/Advanced)
- [x] Paginated note viewer with notebook/paper aesthetic
- [x] Right sidebar with Concepts tab + Doubts tab
- [x] Node popover with status change + practice question generation
- [x] All MongoDB models (users, notebooks with graph embedding)
- [x] Design system: Paper theme, Playfair Display headers, Crimson Pro body

## Testing Status
- Backend: 92.3% pass rate (12/13 tests) 
- Frontend: 100% pass rate
- AI Integration: 100% working (GPT-4o + local fallbacks)
- User Workflows: 100% (registration, login, notebook management, navigation)

## Prioritized Backlog
### P0 (Critical)
- None outstanding

### P1 (High)
- Multi-user graph persistence and sharing
- Real-time note sync across devices
- PDF preview before fusion

### P2 (Medium)
- 3D Knowledge Graph visualization (Three.js)
- Exam trend modeling
- AI-generated concept videos
- MOOC/NPTEL integration

### Next Tasks
- Add ability to edit fused notes directly (inline editing)
- Implement spaced repetition reminders
- Add progress analytics dashboard
- B2B university LMS mode with aggregated learning analytics
