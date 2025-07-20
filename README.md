# 🧱 LEGO Review Intelligence – A Full Stack Data Science Project

Analyze the YouTube ecosystem of LEGO reviews using local LLMs and interactive dashboards.

---

## 🎯 What This Project Does

This project automatically:

1. **Finds LEGO review videos on YouTube** using the set number
2. **Extracts & stores video transcripts**
3. **Analyzes sentiment & detects sponsorships** using a local LLM (e.g. LLaMA 3 via Ollama)
4. **Visualizes trends and insights** in a Streamlit dashboard

---

## 🧠 Key Skills & Technologies

| Category           | Tools Used                                                                 |
|--------------------|----------------------------------------------------------------------------|
| **ETL & APIs**     | `yt-dlp`, `requests`, YouTube scraping                                     |
| **Data Processing**| `SQLite`, `Pandas`, structured JSON                                        |
| **LLM Analysis**   | `LangChain`, `Ollama`, prompt engineering, sentiment/sponsorship detection |
| **Dashboard**      | `Streamlit`, `Plotly`, dark theme, filterable UI                          |
| **Deployment**     | Docker-ready, NGINX + Supervisor for multi-app portfolio integration       |

---

## 🔁 Workflow Overview

```mermaid
graph TD
    A[LEGO Set List (CSV)] --> B[YouTube Search via yt-dlp]
    B --> C[Store Metadata + Transcripts in SQLite]
    C --> D[LLM Analysis via LangChain & Ollama]
    D --> E[Streamlit Dashboard]



🛠️ How to Use (Local Setup)
📦 Clone & install dependencies