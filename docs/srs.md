Absolutely. In fact, I would recommend treating this as a proper **Software Requirements Specification (SRS)** instead of just notes. This document should become the single source of truth that we can refer to in future sessions while building the application incrementally.

Below is the first version of the specification.

---

# AI Learning & Assessment Platform

## Software Requirements Specification (SRS)

**Version:** 1.0
**Author:** Surendra (Product Owner) & ChatGPT
**Status:** Draft / Living Document

---

# 1. Vision

The objective is to build an AI-powered web application that enables students to generate unlimited practice question papers aligned with their school syllabus.

Unlike generic AI chatbots, the application should generate questions that closely follow the student's textbook, uploaded learning material, and current syllabus while still leveraging the intelligence of a Large Language Model (LLM) to produce fresh and unique questions.

Initially, the application will be developed for a single Class 8 student but should be architected to support multiple students, schools, boards, and teachers in the future.

---

# 2. Objectives

The application should:

* Generate unlimited practice papers.
* Follow the uploaded syllabus.
* Produce new questions rather than copying existing ones.
* Allow administrators to continuously expand the knowledge base.
* Be deployable as a web application.
* Minimize operational cost by using open-source technologies.
* Be modular enough to replace local components with cloud services in the future.

---

# 3. Target Users

## Primary Users

### Administrator

Responsibilities:

* Manage subjects
* Manage chapters
* Upload study material
* Upload textbook images
* Upload sample question papers
* Upload worksheets
* Manage knowledge base

---

### Student

Responsibilities:

* Select subject
* Select chapter
* Select question type
* Select difficulty
* Select number of questions
* Generate practice paper

Students never upload study material.

---

# 4. Functional Requirements

## Module 1 – Subject Management

Administrator should be able to:

* Add Subject
* Edit Subject
* Delete Subject
* View Subjects

Example

```
Mathematics

Science

English

Computer
```

---

## Module 2 – Chapter Management

Each subject contains multiple chapters.

Example

```
Mathematics

    Chapter 1 – Rational Numbers

    Chapter 2 – Algebra

    Chapter 3 – Linear Equations
```

Administrator can

* Add Chapter
* Edit Chapter
* Delete Chapter
* Reorder Chapters

---

## Module 3 – Knowledge Base Management

Each chapter should maintain its own knowledge repository.

Supported uploads:

* Book images
* PDFs
* Question papers
* Notes
* Worksheets
* Sample papers

Knowledge can be continuously expanded over time.

---

## Module 4 – OCR Processing

Uploaded images should automatically undergo OCR.

Pipeline

```
Image

↓

OCR

↓

Extract Text

↓

Clean Text

↓

Store
```

Original images should also be preserved.

---

## Module 5 – Knowledge Processing

After OCR

The system should

* chunk documents
* create embeddings
* create metadata
* update vector database

No manual intervention required.

---

## Module 6 – Student Practice Paper Generator

Student inputs

```
Subject

↓

Chapter

↓

Difficulty

↓

Question Types

↓

Number of Questions
```

Output

```
Practice Question Paper
```

---

## Module 7 – Question Types

Initially support

* Multiple Choice Questions
* Fill in the blanks
* True / False
* Short Answer
* Long Answer
* Numerical Problems

Future

* Assertion Reason
* HOTS
* Case Studies

---

## Module 8 – Difficulty Levels

Support

* Easy
* Medium
* Hard

Future

Bloom's Taxonomy

* Remember
* Understand
* Apply
* Analyze

---

## Module 9 – Answer Key

Every generated paper should optionally include

* Answer Key
* Step-by-step solution (future)

---

# 5. Knowledge Sources

Question generation should combine three sources.

## Priority 1

Uploaded knowledge base

(Textbook pages, worksheets, notes)

Highest priority.

---

## Priority 2

LLM General Knowledge

The LLM may use its own understanding to create fresh questions.

It must never introduce concepts outside the selected chapter.

---

## Priority 3

Internet Search (Optional)

Can be enabled for

* latest worksheets
* olympiad patterns
* sample papers
* exam trends

Internet information should only enrich question styles, not change the syllabus.

---

# 6. Question Generation Strategy

Prompt should instruct the LLM to

* Follow uploaded syllabus.
* Use retrieved context.
* Generate fresh questions.
* Avoid duplication.
* Stay within selected chapter.
* Maintain selected difficulty.
* Generate requested question types.

---

# 7. User Interface

## Student Interface

```
Subject

Chapter

Difficulty

Question Type

Number of Questions

Generate
```

Output

```
Question Paper
```

---

## Admin Interface

Dashboard

```
Subjects

Chapters

Upload Material

Knowledge Base

OCR Status

Embedding Status

Preview Documents
```

---

# 8. Knowledge Repository Structure

Example

```
KnowledgeBase

    Mathematics

        Algebra

            images/

            pdf/

            extracted_text/

            metadata/

            embeddings/

    Science

        Force

        Light

        Sound
```

---

# 9. Metadata

Every uploaded document should automatically receive metadata.

Example

```
Board

Class

Subject

Chapter

Keywords

Learning Objectives

Question Types

Difficulty

Upload Date

Source
```

Metadata should be editable by Administrator.

---

# 10. Retrieval Strategy

The retrieval engine should use

* Semantic Search
* Keyword Search

Hybrid retrieval is preferred over vector search alone.

---

# 11. Proposed Architecture

```
                Student

                   │

             Streamlit UI

                   │

               FastAPI

                   │

         Question Generator

                   │

            Prompt Builder

                   │

              Retriever

        ┌──────────┴──────────┐

 Knowledge Base        Web Search

        │                     │

  Chroma Vector DB      Search Tool

        │

     OCR Text

        │

 Local Storage

        │

      Ollama LLM
```

The architecture should remain modular so that any component can be replaced later.

---

# 12. Technology Stack (Version 1)

| Layer       | Technology               |
| ----------- | ------------------------ |
| UI          | Streamlit                |
| Backend     | FastAPI                  |
| LLM         | Ollama                   |
| Models      | Qwen / Gemma / Llama     |
| OCR         | PaddleOCR + Tesseract    |
| Vector DB   | Chroma                   |
| Embeddings  | BAAI BGE / Nomic Embed   |
| Metadata DB | SQLite                   |
| Storage     | Local File System        |
| Search      | DuckDuckGo / Tavily Free |
| Deployment  | Local / VPS / Azure VM   |

---

# 13. Cost Constraints

The initial version should prioritize zero operational cost.

Avoid paid services including:

* Azure OpenAI
* Azure AI Search
* Pinecone
* Paid OCR APIs
* Paid Databases

The design should, however, make it easy to migrate to paid cloud services in the future by replacing implementations behind clear interfaces.

---

# 14. Deployment Strategy

Phase 1

Run locally.

Phase 2

Deploy on personal VPS or Azure VM.

Phase 3

Public web application for school students.

---

# 15. Non-Functional Requirements

The application should be:

* Modular
* Extensible
* Maintainable
* Low Cost
* Easy to Deploy
* Scalable
* Multi-user Ready
* Responsive
* Secure

---

# 16. Future Enhancements

## Assessment

* Online exams
* Automatic evaluation
* Performance tracking
* Weak chapter identification

---

## Personalization

* Adaptive question generation
* Personalized practice plans
* AI tutor
* Learning recommendations

---

## Teacher Features

* Teacher login
* Teacher-created question banks
* Review AI-generated questions
* Publish assignments

---

## Student Analytics

* Accuracy tracking
* Time spent
* Chapter mastery
* Difficulty progression

---

## Multi-Board Support

Future support for

* CBSE
* RBSE
* ICSE
* State Boards

without code changes.

---

# 17. Design Principles

1. **Knowledge-first Generation**: Uploaded content is the primary source of truth.
2. **AI-assisted Creativity**: The LLM generates fresh questions while respecting the syllabus.
3. **Cost-conscious Architecture**: Open-source and free technologies are preferred initially.
4. **Modular Components**: Every major service (OCR, Retrieval, LLM, Search, Storage) should be replaceable without impacting the rest of the system.
5. **Scalability by Design**: The architecture should support growth from a single student to thousands of users.

---

# 18. Suggested Development Roadmap

Rather than building everything at once, I recommend implementing the application in incremental phases:

### Phase 1 – Foundation

* Project setup
* Folder structure
* Streamlit UI
* FastAPI backend
* SQLite database
* Subject and chapter management

### Phase 2 – Knowledge Base

* Image/PDF upload
* OCR pipeline
* Metadata generation
* Chroma vector database
* Hybrid retrieval

### Phase 3 – AI Question Generator

* Ollama integration
* Prompt engineering
* Question generation
* Answer key generation
* Difficulty and question-type support

### Phase 4 – Student Portal

* Student interface
* Practice paper generation
* PDF export
* Session history

### Phase 5 – Deployment & Production

* Authentication
* Multi-user support
* Deployment on Azure VM/VPS
* Performance optimization
* Monitoring and logging

---

## One additional recommendation

Given your software engineering experience, I would evolve this from a simple application into a **production-quality, portfolio-worthy project**. We should treat it like a real enterprise product from day one by maintaining:

* A formal SRS (this document)
* System Architecture Document
* Low-Level Design (LLD)
* API Specification (OpenAPI/Swagger)
* Database Design
* Prompt Engineering Guide
* RAG Design Document
* Deployment Guide
* Test Strategy
* User Manual
* Admin Manual
* Developer Guide
* Product Backlog (epics, user stories, and tasks)

This documentation-first approach will make development smoother, allow us to resume work across future sessions without losing context, and create a project that is suitable for demonstrations, open-source contribution, or even commercialization.
