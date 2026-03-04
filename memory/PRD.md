# AuraGraph - Product Requirements Document

## Project Overview
**Project Title**: AuraGraph: AI That Learns How You Learn  
**Team**: Wowffulls | IIT Roorkee  
**Challenge Area**: AI Study Buddy  
**Date**: June 2, 2025

## Architecture
- **Frontend**: React CRA + Tailwind CSS + Redux Toolkit (port 3000)
- **Backend**: FastAPI + MongoDB (port 8001, /api prefix)
- **AI**: OpenAI GPT-4o via Emergent LLM Key
- **Design**: Black & white theme. Fonts: Sora, DM Sans, Source Serif 4

## What's Been Implemented
- [x] Full auth, dashboard, notebook CRUD
- [x] Knowledge Fusion (GPT-4o) - all topics covered
- [x] Dynamic Note Mutation - full flow working
- [x] Examiner Agent, Concept Graph
- [x] Black & white theme for laptops
- [x] **BUG FIX**: LaTeX delimiters (\\( \\) -> $ $, \\[ \\] -> $$ $$)
- [x] **BUG FIX**: Beginner mode now detailed & comprehensive
- [x] **BUG FIX**: Mutation properly rewrites notes with intuition block

## Testing Status (Iteration 3)
- Backend: 100% | Frontend: 100% | Mutation flow: verified via screenshot

## Backlog
### P1: Inline note editing, PDF preview, spaced repetition
### P2: 3D graph, exam trend modeling, B2B LMS mode
