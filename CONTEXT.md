# DIA Harness Skills

This repository is the authoritative source for reusable skills that extend TritonAI Harness for DIA staff.

## Language

**Skill library**:
The reviewed collection of team-owned skills stored in this repository.
_Avoid_: Agent library, prompt library

**Source skill**:
The authoritative copy of a skill in this repository. Staff install or synchronize this copy into TritonAI Harness.
_Avoid_: Canonical skill, master skill

**Installed skill**:
A runtime copy of a source skill inside a staff member's TritonAI Harness environment. Changes to an installed skill do not change the source skill.
_Avoid_: Source skill

**Local project folder**:
A staff member's top-level local directory for one DIA project, named after its connected ClickUp Folder and organized according to a versioned layout.
_Avoid_: Project workspace, Local workspace

**Project manifest**:
A local project's machine-readable identity, including its supported type and connected ClickUp resources by stable ID.
_Avoid_: Workspace configuration, Project settings file

**Business insights project**:
A DIA project that produces stakeholder insight through analysis and may result in data products, presentations, or both.
_Avoid_: Reporting project, Dashboard project

**Deliverable**:
A stakeholder-facing outcome produced by a DIA project.
_Avoid_: Output, Artifact

**Requirements document**:
A decision-driven document produced from a business-owner requirements conversation, capturing the decision it supports, the audience and decision context, key questions, data requirements, functional requirements, acceptance criteria, constraints and assumptions, out-of-scope items, and open questions, with meeting capture preserved in an appendix.
_Avoid_: Requirements spec, Business requirements document

**Process outline**:
A readable intermediate document produced from a transcript or a requirements document that identifies the process boundary, actors, ordered steps, decisions, handoffs, systems, and a current-state ROI baseline before any diagram is rendered. It requires explicit user confirmation.
_Avoid_: Process inventory, Workflow draft

**Process inventory**:
A short chat-level list of the plausible processes in one transcript, with actors, trigger, end point, evidence strength, and likely role. It is presented before any outline is written and is confirmed by the user.
_Avoid_: Process catalog, Workflow scan

**Current-state ROI baseline**:
The measured or explicitly gap-flagged current-state effort, elapsed time, handoffs, rework, and volume for one process, with stated sources and confidence. It provides the comparison point for a future-state delta and is never silently incomplete.
_Avoid_: Timing table, Time estimate

**Project Request draft**:
A first-pass, field-by-field fill-in document produced from a transcript that records proposed answers for the VCFA DIA Project Request Form, with evidence for each answer and explicit data gaps for anything the transcript does not support. It requires human review before any submission.
_Avoid_: Intake form, Ticket draft

**KPI facts file**:
The schema-versioned YAML file recorded beside a business-questions-and-KPIs document that holds confirmed business questions and KPIs with their attribution and open questions.
_Avoid_: KPI list, Metrics spec

**KPI data mapping report**:
A declarative document that maps confirmed KPIs to the fields of one dataset, defines the calculations to build, and flags data gaps.
_Avoid_: Field mapping, Data dictionary

**Workbook facts file**:
The schema-versioned YAML file recorded beside a Tableau workbook package that holds deterministic facts about its dashboards, dashboard-used sheets, filters, parameters, and calculations.
_Avoid_: Workbook inventory, TWB extract

**Data product**:
A reusable analytical deliverable through which stakeholders access or use data, such as a Tableau dashboard.
_Avoid_: Dashboard file, Report

**Dashboard mockup**:
A self-contained HTML prototype of a data product, rendered from a KPI data mapping report with mock data and explicit data-gap panels. It is a review artifact, never a working dashboard.
_Avoid_: Prototype, Wireframe

**Analysis workspace**:
The per-file working area under `scratch/analysis/` of a data-analysis workspace, holding one analysis link, recorded questions, and their SQL.
_Avoid_: Business-analysis space, Analysis area

**Data analysis workspace**:
A fresh local working area for one analysis project, holding immutable raw inputs, numbered pipeline scripts, dashboard-ready output, and meeting transcripts with their derived documents. It is not connected to ClickUp or GitHub.
_Avoid_: Analytics workspace, Data project scaffold

**Source file**:
The user-selected CSV or Excel file that supplies the data for an analysis workspace. It stays in place and is never copied.
_Avoid_: Input file, Dataset file

**Analysis link**:
The recorded association between an analysis folder and its source file, including the file hash. Queries fail when the file no longer matches the recorded hash.
_Avoid_: Snapshot, Working copy, Imported file

**Analysis question**:
A business question answered from an analysis workspace and recorded with the SQL used to answer it.
_Avoid_: Query request, Data question

**Workspace re-link**:
An explicit re-creation of an analysis link after its source file changed. Earlier analysis questions remain associated with the link that produced their answers.
_Avoid_: Automatic update, Data sync

**Connection skill**:
A skill that configures and verifies access from TritonAI Harness to an external service. It does not define day-to-day workflows in that service.
_Avoid_: Integration workflow, task-management skill

**Team destination**:
A shared ClickUp location approved for DIA work. Team destinations may be identified by stable workspace, space, or list IDs stored in the repository.
_Avoid_: Personal destination

**DIA Space**:
The shared ClickUp space where DIA staff manage team work.
_Avoid_: DIA list, Personal List

**My Tasks**:
The authenticated staff member's ClickUp view of work assigned to them across the Workspace. It is not a List or a team destination and has no shared destination ID.
_Avoid_: Personal List, Personal destination
