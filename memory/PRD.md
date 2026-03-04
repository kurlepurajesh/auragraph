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
- **Design**: Black & white theme. Fonts: Sora (headings), DM Sans (UI), Source Serif 4 (study text)

## User Personas
1. **Rahul** - Overwhelmed engineering student needing fused notes
2. **Ananya** - Top performer wanting depth + targeted practice

## Core Requirements
1. Knowledge Fusion - Upload slides + textbook PDFs → unified notes
2. Dynamic Note Mutation - Highlight confusing text → AI rewrites permanently
3. Cognitive Knowledge Graph - Visual mastery map (black/grey/red nodes)
4. Sniper Examiner - Targeted MCQ practice questions
5. Auth - JWT-based email/password
6. Notebook Management - CRUD with MongoDB

## What's Been Implemented
- [x] Full auth system (register/login)
- [x] Dashboard with notebook CRUD, search
- [x] Notebook Workspace with dual PDF upload
- [x] Knowledge Fusion (GPT-4o + local fallback)
- [x] Dynamic Note Mutation with doubt modal
- [x] Examiner Agent generating MCQs
- [x] Concept Extraction → SVG Knowledge Graph
- [x] Proficiency Level selector (Beginner/Intermediate/Advanced)
- [x] Paginated note viewer
- [x] Right sidebar (Concepts + Doubts tabs)
- [x] **REDESIGN**: Black & white website theme for laptop screens (v2)

## Testing Status (Iteration 2)
- Frontend: 100% | Theme: 100% | Workflows: 100%
- Backend: 84.6% (fuse timeout on direct call, works via upload)

## Backlog
### P1: Inline note editing, PDF preview, spaced repetition
### P2: 3D graph (Three.js), exam trend modeling, B2B LMS mode
