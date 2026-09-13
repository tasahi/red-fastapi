---
title: Technical Documentation Index
document_type: Documentation Hub / Table of Contents
project: red-fastapi
status: Completed
phases:
  phases_completed: 13/13 (Phases 1 through 13 Operational)
date: September 2026
---

# Technical Documentation Index

**Project:** `red-fastapi`  
**Document Type:** Documentation Hub / Table of Contents  
**Status:** All 13 Phases Completed (69/68 Automated Tests Passing)  
**Date:** September 2026  

---

## Overview

Welcome to the technical documentation repository for **`red-fastapi`**, an asynchronous Python (FastAPI) runtime implementation of the Node-RED visual execution engine that operates with 100% wire-protocol compatibility against the stock `@node-red/editor-client` frontend.

---

## Documentation Directory

| Document | Description | Type |
| :--- | :--- | :--- |
| **[fast-api_basics.md](./fast-api_basics.md)** | Objectives & Key Findings (OKF) technical specification document. Includes frontend/backend codebase SLOC distribution, core REST/WebSocket wire protocols, and upstream sync architecture. | OKF Specification |
| **[production_and_phases.md](./production_and_phases.md)** | Production deployment architecture (Apache ingress / reverse proxy), S3/MinIO & Local storage configuration, test suite summary, code style conventions, and exhaustive phase-by-phase implementation statuses (Phases 1–13). | Architecture & Roadmap |
| **[implementation_plan.md](./implementation_plan.md)** | Comprehensive implementation roadmap detailing architectural requirements, file layout, and component-by-component implementation strategies. | Implementation Plan |
| **[gap_analysis.md](./gap_analysis.md)** | In-depth technical gap analysis comparing Node-RED (Node.js runtime) vs Red-FastAPI (Python asyncio engine), node coverage, and behavioral differences. | Gap Analysis |
| **[plan_core_and_sequence_nodes.md](./plan_core_and_sequence_nodes.md)** | Specific design and verification plan for Core Execution, Sequence, and Flow Control nodes. | Technical Design |
| **[subflow_plan.md](./subflow_plan.md)** | Subflow execution runtime architecture, port mapping, scoped environments, and nested subflow routing. | Technical Design |

---

## Quick Links

- **Main Repository Overview:** [README.md](../README.md)
- **License:** [Apache 2.0 License](../LICENSE)
- **Upstream Sync Utility:** `npm run update:upstream` ([scripts/sync-upstream.js](../scripts/sync-upstream.js))

