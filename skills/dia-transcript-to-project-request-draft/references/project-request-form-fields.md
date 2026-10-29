# VCFA - DIA - Project Request Form Field Map

Source of truth: the live form at https://forms.clickup.com/1275695/f/16xtf-14894/E4ONXMVAEJ5SXTPLT8 ("VCFA - DIA - Project Request Form"). Re-check the live form if a field, required marker, or option looks different; form owners can change fields without notice.

Form introduction shown to submitters: "Let's get your project started! Use this form to initiate your project and ensure it aligns with our strategic company initiatives. The goal is to help us understand the business need, background, and desired impact - so we can design analytics and insight-driven solutions, and determine what it will take to turn your vision into reality."

## Section: Contact and Team Detail

| Field | Required | Input | Form description |
| --- | --- | --- | --- |
| Primary Contact | Yes | Short text | None |
| Primary Contact / Lead Email | Yes | Email | None |
| Department / Unit | Yes | Single-select dropdown | None |
| Other Teams | No | Multi-select dropdown | "List any other teams that should be involved, particularly if KPI definition or alignment needed across campus" |
| Executive Sponsor | Yes | Short text | None |

## Section: Project Detail

Section introduction: "Give as many details as you can, so our project committee can ensure that resources are effectively allocated. This helps your project be completed on time and within budget."

| Field | Required | Input | Form description |
| --- | --- | --- | --- |
| Project Title | Yes | Short text | "Include high level description of the ask and primary team supported" |
| Details | Yes | Rich text | "Please include links to any meeting notes, Docs, tasks, or information that will be helpful. Information around requirements, constraints, and guidelines or direction, as well as understanding challenges, teams impacted, etc." |
| Data and System Dependencies | No | Rich text | "What data is required for this? (If known) What is the current access / availability / maturity of the data. What systems do the data source from and are they in a data repository / warehouse. (Goal: to understand data maturity and assess possible work / scope)" |
| Business Outcome | No | Rich text | "What is the Strategic Alignment, Business Outcome or Action from this project and who will own it? When the final product is delivered, what change or impact should we expect to measure or see? Success definition criteria?" |
| Project Type | No | Single-select dropdown | None |
| Primary Goal | No | Single-select dropdown | None |
| Metric/KPI alignment | No | Short text | None |
| Due Date | Yes | Date picker | None |
| Attachments | No | File upload | "Add any attachments with relevant information and context." |
| Documentation Link | No | URL | None |

## Dropdown options

Department / Unit: `Campus / VCs`, `Exec Leadership`, `Finance`, `HR`, `ITS`, `RRSS`, `Other`, `data`.

Other Teams: `Academic Services`, `Finance and Administration`, `Health Services`, `IR`, `Research and Grants`, `SIO (Scripps)`, `Student Services`.

Project Type: `Data - New / Edit / Governance`, `Insight - Deck / Analysis / Process Improvement`, `Analytics - Report / Dashboard / AI`, `Other - Consulting / etc.`

Primary Goal: `Analysis`, `Compliance`, `Cost/Time Optimization`, `Growth/Revenue`, `Process/KPI Optimization`, `Standard Reporting`.

## Drafting guidance per field

- **Primary Contact**: the business owner or lead who owns the request, not the DIA analyst filling the form. Use the name exactly as the transcript supports it.
- **Primary Contact / Lead Email**: email addresses are rarely spoken. Expect a Gap; the question to resolve is the requester's email address.
- **Department / Unit**: map the requester's organization to one documented option. If the transcript does not place the requester in an org, leave a Gap.
- **Other Teams**: only when the transcript names cross-team involvement or campus-wide KPI alignment. Team names the transcript mentions that are not in the option list go in the draft as a note for the user, not as invented options.
- **Executive Sponsor**: a named leader accountable for the project. A stakeholder who is merely involved or mentioned is not a sponsor; record them in Details instead and leave a Gap when no sponsor is stated.
- **Project Title**: one line combining the ask and the primary team supported, per the form's own hint.
- **Details**: background, the request itself, intended uses, conditions or practices the requester commits to, scope considerations, and open technical questions. Attribute key positions to speakers.
- **Data and System Dependencies**: systems named, where the data lives today, its availability and maturity, and anything unknown about extraction or warehouse presence.
- **Business Outcome**: the change the requester expects, who owns the outcome, and any success criteria stated. When the transcript states no success criteria, say so in the draft instead of inventing them.
- **Project Type**: pick from the documented options; note alternatives as Confirm when the transcript supports more than one.
- **Primary Goal**: same rule as Project Type.
- **Metric/KPI alignment**: concrete measures the transcript supports, written compactly. When nothing measures the outcome, leave a Gap.
- **Due Date**: keep the transcript's relative wording in Evidence, propose a concrete placeholder date in the draft, and set Status to Confirm.
- **Attachments**: note the transcript file by name; the user attaches it manually.
- **Documentation Link**: only a URL the transcript cites. A ticket number without a URL stays a named gap or a Details reference.
