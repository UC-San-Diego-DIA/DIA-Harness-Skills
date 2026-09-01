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

**Data product**:
A reusable analytical deliverable through which stakeholders access or use data, such as a Tableau dashboard.
_Avoid_: Dashboard file, Report

**Analysis workspace**:
A local working area for one source CSV and the ad hoc analysis derived from it.
_Avoid_: Business-analysis space, Analysis area

**Source CSV**:
The user-selected CSV that supplies the data for an analysis workspace.
_Avoid_: Input file, Dataset file

**Dataset snapshot**:
The copy of a source CSV held by an analysis workspace so later questions use the same data.
_Avoid_: Working copy, Imported file

**Analysis question**:
A business question answered from an analysis workspace and recorded with the SQL used to answer it.
_Avoid_: Query request, Data question

**Workspace refresh**:
An explicit replacement of an analysis workspace's dataset snapshot. Earlier analysis questions remain associated with the snapshot that produced their answers.
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
